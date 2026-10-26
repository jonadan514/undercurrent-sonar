"""신호 성과 검증 배치 — 과거 주간 워치리스트 후보에 실제 주가를 대조해 여러 기간 후 수익률을 계산한다.

watchlist_candidate_history(매주 스크리닝 시점 스냅샷 — 절대 덮어쓰지 않는 이력 테이블)를
읽어, 각 종목의 스크리닝일 이후 30/60/90/180/365/730일 시점 종가와 대조해 수익률을 계산하고
data_pick_returns / kr_pick_returns에 저장한다.
180일 이상(6개월/1년/2년) 창은 1~3년 펀더멘털 보유를 검증하기 위한 것 — 30/60/90일은
과거 스윙 트레이딩 시절 데이터 호환용으로 남겨둔다.
같은 방식으로 벤치마크(SPY / ^KS11)의 기간별 수익률도 data_benchmark_returns /
kr_benchmark_returns에 저장해, "필터 통과 종목 vs 지수 단순 보유" 비교의 기준선을 만든다.

멱등적으로 재실행 가능 — 아직 N일이 지나지 않아 계산 못 한 항목은 NULL로 남고,
다음 실행(주 1회 권장) 때 시간이 지나 계산 가능해지면 채워진다. 이미 채워진 값은
덮어쓰지 않는다(COALESCE).

Usage:
  python scripts/compute_pick_returns.py --market US
  python scripts/compute_pick_returns.py --market KR
  python scripts/compute_pick_returns.py --market ALL   (기본값)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db.data_store import get_db
from src.collectors.us_price_fetcher import USPriceFetcher

HORIZONS = (30, 60, 90, 180, 365, 730)  # 달력일 기준 — 180/365/730일은 장기(6개월/1년/2년) 검증용
RET_COLS = [f"fwd_{h}d_ret" for h in HORIZONS]

MARKET_CONFIG = {
    "US": {
        "returns_table":   "data_pick_returns",
        "bench_table":     "data_benchmark_returns",
        "benchmark":       "SPY",
    },
    "KR": {
        "returns_table":   "kr_pick_returns",
        "bench_table":     "kr_benchmark_returns",
        "benchmark":       "^KS11",
    },
}

CANDIDATE_HISTORY_TABLE = "watchlist_candidate_history"

# 한국 종목코드 -> yfinance 티커 매핑 파일(수집기가 만들어 저장소에 커밋해 둔 것).
KR_UNIVERSE_PATH = ROOT / "data" / "kr_universe.json"


def _kr_yf_symbol(symbol: str, universe: dict[str, str]) -> str:
    """'005930' -> '005930.KS'. yfinance는 접미사 없는 한국 종목코드를 못 알아본다.

    2026-09-30까지 이 변환이 없어서 한국 성적표가 통째로 비어 있었다 - 가격 조회가
    전부 빈 결과를 돌려주는데도 upsert 자체는 성공해서(전부 NULL) 로그만 보면
    정상으로 보였다. 벤치마크(^KS11)는 접미사가 필요 없어 그쪽만 값이 있었고,
    그래서 "지수 대비 비교"의 한쪽이 영원히 비어 있었다.

    유니버스 파일에 없는 종목(상장폐지·유니버스 변경 등)은 .KS로 시도한다 -
    후보 집단이 대형주 쪽에 쏠려 있어 코스피일 확률이 높고, 틀리면 그 종목만
    값이 안 채워질 뿐 다음 실행에서 다시 시도된다(멱등적).
    """
    mapped = universe.get(symbol)
    if mapped:
        return mapped
    return symbol if "." in symbol else f"{symbol}.KS"


def _load_kr_universe() -> dict[str, str]:
    try:
        items = json.loads(KR_UNIVERSE_PATH.read_text(encoding="utf-8")).get("items", [])
    except Exception as e:
        _log(f"경고 - kr_universe.json을 읽지 못했다({type(e).__name__}). .KS로 폴백한다.")
        return {}
    return {it["symbol"]: it["yf_symbol"] for it in items
            if it.get("symbol") and it.get("yf_symbol")}


def _returns_ddl(table: str) -> str:
    cols = ",\n        ".join(f"{c} REAL" for c in RET_COLS)
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
            date         TEXT NOT NULL,
            symbol       TEXT NOT NULL,
            grade        TEXT,
            gate         TEXT,
            regime       TEXT,
            action       TEXT,
            entry_price  REAL,
            {cols},
            updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (date, symbol)
        )
    """


def _bench_ddl(table: str) -> str:
    cols = ",\n        ".join(f"{c} REAL" for c in RET_COLS)
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
            date         TEXT NOT NULL PRIMARY KEY,
            ticker       TEXT NOT NULL,
            entry_price  REAL,
            {cols},
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """


def _ensure_ret_columns(conn, table: str) -> None:
    """이미 배포되어 있던 테이블(30/60/90일 컬럼만 있음)에 새 기간 컬럼을 뒤늦게 추가.
    컬럼이 이미 있으면 에러를 무시한다 — 멱등적으로 여러 번 실행해도 안전."""
    for col in RET_COLS:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} REAL")
        except Exception:
            pass


def _log(msg: str) -> None:
    print(f"[compute_pick_returns] {msg}")


def _load_candidate_history(conn, market: str) -> list[dict]:
    """watchlist_candidate_history를 screened_date별로 묶어 과거 daily-report 형태로 변환.
    (gate/regime은 후보 목록엔 없는 개념이라 None — 스키마 호환을 위해 컬럼만 남김)"""
    rows = conn.execute(
        f"SELECT screened_date, symbol, piotroski, regime_fit, current_price "
        f"FROM {CANDIDATE_HISTORY_TABLE} WHERE market = ? ORDER BY screened_date ASC",
        (market,),
    ).fetchall()

    by_date: dict[str, list[dict]] = {}
    for r in rows:
        d, sym, piotroski, regime_fit, price = r[0], r[1], r[2], r[3], r[4]
        by_date.setdefault(d, []).append({
            "symbol": sym, "piotroski": piotroski, "regime_fit": regime_fit,
            "current_price": price,
        })
    return [
        {"date": d, "regime": None, "gate": None, "picks": picks}
        for d, picks in sorted(by_date.items())
    ]


def _completed(df: pd.DataFrame | None, today: date) -> pd.DataFrame | None:
    """오늘 날짜 막대를 뺀다 - 장중에 받은 오늘 '종가'는 그 시각 가격이다. 정기 실행이 월요일 한국 장중에 돌아
    한국 지수 시작가·끝가가 장중 가격으로 채워지고 COALESCE로 굳었다(2026-10-26 점검, signal_check.completed_bars와 같은 규칙)."""
    if df is None or df.empty:
        return df
    return df[df.index < pd.Timestamp(today)]


def _price_on_or_after(df: pd.DataFrame, target: pd.Timestamp) -> float | None:
    if df is None or df.empty:
        return None
    sub = df[df.index >= target]
    if sub.empty:
        return None
    return float(sub.iloc[0]["Close"])


def _fwd_returns(df: pd.DataFrame, entry_date: date, entry_price: float | None) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    today = date.today()
    for h in HORIZONS:
        target_date = entry_date + timedelta(days=h)
        key = f"fwd_{h}d_ret"
        if today < target_date or entry_price in (None, 0):
            out[key] = None
            continue
        fwd_price = _price_on_or_after(df, pd.Timestamp(target_date))
        out[key] = (fwd_price - entry_price) / entry_price if fwd_price is not None else None
    return out


def _upsert_pick_return(conn, table: str, date_str: str, symbol: str, grade, gate, regime, action,
                         entry_price, fwd: dict[str, float | None]) -> None:
    ret_col_list = ", ".join(RET_COLS)
    ret_placeholders = ", ".join("?" for _ in RET_COLS)
    ret_coalesce = ",\n            ".join(f"{c} = COALESCE(excluded.{c}, {table}.{c})" for c in RET_COLS)
    conn.execute(f"""
        INSERT INTO {table} (date, symbol, grade, gate, regime, action, entry_price,
                              {ret_col_list}, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, {ret_placeholders}, datetime('now'))
        ON CONFLICT(date, symbol) DO UPDATE SET
            grade        = excluded.grade,
            gate         = excluded.gate,
            regime       = excluded.regime,
            action       = excluded.action,
            entry_price  = COALESCE(excluded.entry_price, {table}.entry_price),
            {ret_coalesce},
            updated_at   = datetime('now')
    """, (date_str, symbol, grade, gate, regime, action, entry_price,
          *[fwd.get(c) for c in RET_COLS]))


def _upsert_benchmark_return(conn, table: str, date_str: str, ticker: str,
                              entry_price, fwd: dict[str, float | None]) -> None:
    ret_col_list = ", ".join(RET_COLS)
    ret_placeholders = ", ".join("?" for _ in RET_COLS)
    ret_coalesce = ",\n            ".join(f"{c} = COALESCE(excluded.{c}, {table}.{c})" for c in RET_COLS)
    conn.execute(f"""
        INSERT INTO {table} (date, ticker, entry_price, {ret_col_list}, updated_at)
        VALUES (?, ?, ?, {ret_placeholders}, datetime('now'))
        ON CONFLICT(date) DO UPDATE SET
            entry_price  = COALESCE(excluded.entry_price, {table}.entry_price),
            {ret_coalesce},
            updated_at   = datetime('now')
    """, (date_str, ticker, entry_price, *[fwd.get(c) for c in RET_COLS]))


def run(market: str) -> None:
    cfg = MARKET_CONFIG[market]
    conn = get_db()
    conn.execute(_returns_ddl(cfg["returns_table"]))
    conn.execute(_bench_ddl(cfg["bench_table"]))
    _ensure_ret_columns(conn, cfg["returns_table"])
    _ensure_ret_columns(conn, cfg["bench_table"])

    reports = _load_candidate_history(conn, market)
    _log(f"{market}: {len(reports)}개 주간 스크리닝 스냅샷 로드")
    if not reports:
        return

    # 종목별로 필요한 가격 시계열을 한 번씩만 가져오기 위해 먼저 유니버스 수집
    symbols: set[str] = set()
    for r in reports:
        for p in r["picks"]:
            sym = p.get("symbol")
            if sym:
                symbols.add(sym)

    fetcher = USPriceFetcher()
    earliest = min(date.fromisoformat(r["date"]) for r in reports)
    days_span = (date.today() - earliest).days + max(HORIZONS) + 5
    # 730일(2년) 전방 창까지 커버해야 하므로 넉넉하게 5y까지 확보
    period = "5y" if days_span > 365 else "1y"

    # 한국은 종목코드에 거래소 접미사를 붙여야 yfinance가 알아듣는다. 표에 저장하는
    # 키는 원래 종목코드 그대로 두고(watchlist_candidate_history와 맞춰야 한다),
    # 가격 조회용 티커만 따로 만든다.
    kr_universe = _load_kr_universe() if market == "KR" else {}
    fetch_symbol = (
        (lambda s: _kr_yf_symbol(s, kr_universe)) if market == "KR" else (lambda s: s)
    )

    price_cache: dict[str, pd.DataFrame] = {}
    _log(f"{market}: 종목 {len(symbols)}개 + 벤치마크({cfg['benchmark']}) 가격 조회 시작 (period={period})")
    for i, sym in enumerate(sorted(symbols), 1):
        price_cache[sym] = _completed(fetcher.fetch_ohlcv(fetch_symbol(sym), period=period), date.today())
        if i % 25 == 0:
            _log(f"  {i}/{len(symbols)+1} 조회 완료")
        time.sleep(0.2)  # 레이트리밋 여유
    # 벤치마크(SPY/^KS11)는 접미사 변환 대상이 아니다 - 그대로 조회한다.
    price_cache[cfg["benchmark"]] = _completed(fetcher.fetch_ohlcv(cfg["benchmark"], period=period), date.today())

    empty = sum(1 for s in symbols if price_cache.get(s) is None or price_cache[s].empty)
    if empty:
        _log(f"  경고 - 가격을 못 받은 종목 {empty}/{len(symbols)}개 (그 종목은 수익률이 NULL로 남는다)")

    bench_df = price_cache.get(cfg["benchmark"])

    total = 0
    for r in reports:
        entry_date = date.fromisoformat(r["date"])

        # 벤치마크
        bench_entry = _price_on_or_after(bench_df, pd.Timestamp(entry_date))
        bench_fwd = _fwd_returns(bench_df, entry_date, bench_entry)
        _upsert_benchmark_return(conn, cfg["bench_table"], r["date"], cfg["benchmark"], bench_entry, bench_fwd)

        for p in r["picks"]:
            sym = p.get("symbol")
            if not sym:
                continue
            entry_price = p.get("current_price")
            df = price_cache.get(sym)
            fwd = _fwd_returns(df, entry_date, entry_price)
            _upsert_pick_return(
                conn, cfg["returns_table"], r["date"], sym,
                p.get("piotroski"), r["gate"], r["regime"], p.get("regime_fit"),
                entry_price, fwd,
            )
            total += 1

    conn.commit() if hasattr(conn, "commit") else None
    _log(f"{market}: 총 {total}개 픽 수익률 upsert 완료")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=["US", "KR", "ALL"], default="ALL")
    args = parser.parse_args()

    markets = ["US", "KR"] if args.market == "ALL" else [args.market]
    for m in markets:
        run(m)


if __name__ == "__main__":
    main()
