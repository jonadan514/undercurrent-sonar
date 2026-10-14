"""미국 기업 분기 재무(매출·영업이익·순이익)를 yfinance에서 모아 quarterly_financials_raw에
저장한다.

분기 재설계 docs/REDESIGN_SPEC.md 4-1. 한국(collect_kr_quarterly_financials.py)과 짝을
이루지만 출처가 달라 세 가지가 다르다.
  - **연결·별도 구분이 없다.** fs_div=None으로 넣으면 insert_quarter()가 "NA"로 저장한다 -
    quarterly_financials.py가 애초에 이 경우("yfinance는 연결·별도 구분이 없다")를 위해
    설계돼 있다.
  - **4분기를 따로 계산하지 않는다.** yfinance quarterly_financials는 분기별 값을 직접
    준다 - DART처럼 연간에서 9개월 누적을 빼는 계산이 필요 없다.
  - **무료 API가 사실상 5분기까지만 준다**(2026-09-01 확인, `theme_earnings.py` 참고).
    그 이상 있는 종목도 오래된 분기는 값이 비어 있는 경우가 많다.

Rate limit 대응은 기존 backfill_quarterly_financials.py(구 주간 시스템, fundamentals_cache에
저장 - 이 스크립트와는 다른 표에 쓴다)와 같은 백오프를 쓴다.

Usage:
  python scripts/collect_us_quarterly_financials.py                    # US 유니버스 전체
  python scripts/collect_us_quarterly_financials.py --tickers AAPL MSFT
  python scripts/collect_us_quarterly_financials.py --offset 250 --limit 250  # 구간 실행
  python scripts/collect_us_quarterly_financials.py --only-missing     # 표에 아직 없는 종목만
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.db.data_store import get_db
from src.db.quarterly_financials import ensure_schema, insert_quarter, migrate_legacy_rows
from collectors.watchlist_collector import get_us_universe

RATE_LIMIT_BACKOFF = [60, 180, 600]
CALL_SLEEP = 1.0
REVENUE_KEYS = ("Total Revenue",)
OPERATING_INCOME_KEYS = ("Operating Income", "EBIT")   # 없으면 EBIT으로 대신한다
NET_INCOME_KEYS = ("Net Income",)


def _log(msg: str) -> None:
    print(f"[us-fin] {msg}", flush=True)


def quarter_of(ts) -> tuple[int, int]:
    """yfinance 분기 열의 날짜(분기 말일)에서 (연도, 분기)를 뽑는다."""
    return ts.year, (ts.month - 1) // 3 + 1


def _first_value(series: pd.Series, keys: tuple[str, ...]) -> float | None:
    """keys를 순서대로 찾아 첫 번째로 있는 값을 쓴다(예: Operating Income 없으면 EBIT)."""
    for key in keys:
        if key in series.index:
            v = series.loc[key]
            if not pd.isna(v):
                return float(v)
    return None


def extract_quarters(df: pd.DataFrame) -> dict[tuple[int, int], dict]:
    """yfinance quarterly_financials DataFrame(행=계정과목, 열=분기 말일)을
    {(연도, 분기): {"revenue", "operating_income", "net_income", "fs_div": None}}로 바꾼다.

    세 값이 다 없는 분기는 뺀다(원칙 4와 무관 - "그 분기 자체가 없다"와 "값이 비었다"는
    insert_quarter 이후에도 구분되지 않으므로, 여기서 걸러야 나중에 select_quarters()가
    쓸모없는 빈 분기를 "최근 분기"로 잘못 짚지 않는다).
    """
    out: dict[tuple[int, int], dict] = {}
    for col in df.columns:
        series = df[col]
        revenue = _first_value(series, REVENUE_KEYS)
        op = _first_value(series, OPERATING_INCOME_KEYS)
        net = _first_value(series, NET_INCOME_KEYS)
        if revenue is None and op is None and net is None:
            continue
        out[quarter_of(col)] = {"revenue": revenue, "operating_income": op,
                                "net_income": net, "fs_div": None}
    return out


def fetch_quarterly(ticker: str) -> tuple[pd.DataFrame | None, str]:
    """반환: (DataFrame|None, ""|"rate_limited"|"no_data"|"error")."""
    attempt = 0
    while True:
        try:
            df = yf.Ticker(ticker).quarterly_financials
            if df is None or df.empty:
                return None, "no_data"
            return df, ""
        except YFRateLimitError:
            if attempt < len(RATE_LIMIT_BACKOFF):
                wait = RATE_LIMIT_BACKOFF[attempt]
                attempt += 1
                _log(f"  {ticker}: rate limit - {wait}초 대기 후 재시도 "
                     f"({attempt}/{len(RATE_LIMIT_BACKOFF)})")
                time.sleep(wait)
                continue
            return None, "rate_limited"
        except Exception as e:  # noqa: BLE001 - 한 종목 실패로 전체를 멈추지 않는다
            _log(f"  {ticker}: 실패 {type(e).__name__}: {str(e)[:120]}")
            return None, "error"


_VALUE_KEYS = ("revenue", "operating_income", "net_income")


def _same(a, b) -> bool:
    """저장값(Turso는 문자열로 돌려줄 수 있다)과 새 값이 같은가. 둘 다 없으면 같다."""
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= max(1.0, abs(float(b)) * 1e-9)


def changed_quarters(quarters: dict[tuple[int, int], dict],
                     latest: dict[tuple[int, int], tuple]) -> dict[tuple[int, int], dict]:
    """저장할 분기만 남긴다 - 처음 보는 분기이거나, 마지막으로 저장한 값과 하나라도 다른 분기.

    quarterly_financials_raw는 수집일(collected_on)마다 행을 쌓는 이력 표다. 정기 실행이
    매주 전체 유니버스를 다시 받으면 값이 그대로여도 주당 약 4,500행(900종목 x 5분기)이
    쌓인다. 값이 바뀐 경우(정정 공시 등)는 새 행으로 남겨 이력 원칙은 그대로 지킨다."""
    out = {}
    for key, v in quarters.items():
        prev = latest.get(key)
        if prev is None or not all(_same(p, v.get(k)) for p, k in zip(prev, _VALUE_KEYS)):
            out[key] = v
    return out


def load_latest_values(conn) -> dict[str, dict[tuple[int, int], tuple]]:
    """종목·분기별 마지막으로 저장된 (매출, 영업이익, 순이익). 한 번의 쿼리로."""
    rows = conn.execute(
        "SELECT ticker, fiscal_year, fiscal_quarter, revenue, operating_income, net_income "
        "FROM quarterly_financials_raw WHERE market = 'US' AND source = 'yfinance' "
        "ORDER BY collected_on"
    ).fetchall()
    out: dict[str, dict[tuple[int, int], tuple]] = {}
    for t, y, q, rev, op, net in rows:
        out.setdefault(t, {})[(int(y), int(q))] = (rev, op, net)   # 뒤(최근)가 앞을 덮는다
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", default=None, help="종목코드 몇 개만 (확인용)")
    ap.add_argument("--offset", type=int, default=0, help="유니버스 정렬 순서에서 이만큼 건너뛴다")
    ap.add_argument("--limit", type=int, default=None, help="offset부터 N개만")
    ap.add_argument("--only-missing", action="store_true",
                    help="quarterly_financials_raw에 행이 하나도 없는 종목만. 유니버스가 넓어졌을 때 "
                         "(2026-10 S&P 400 편입 후 중형주 전부가 비어 PSR이 안 나왔다) 새 종목만 채운다")
    args = ap.parse_args()

    tickers = args.tickers or sorted(it["symbol"] for it in get_us_universe())
    if args.offset or args.limit:
        end = args.offset + args.limit if args.limit else None
        tickers = tickers[args.offset:end]

    conn = get_db()
    ensure_schema(conn)
    moved = migrate_legacy_rows(conn)   # 예전 테이블 값을 raw로 옮긴다(여러 번 돌려도 안전)
    if moved:
        _log(f"예전 테이블에서 {moved}행을 원본 테이블로 옮겼다")

    if args.only_missing:
        have = {r[0] for r in conn.execute(
            "SELECT DISTINCT ticker FROM quarterly_financials_raw WHERE market = 'US'").fetchall()}
        before = len(tickers)
        tickers = [t for t in tickers if t not in have]
        _log(f"표에 이미 있는 {before - len(tickers)}종목은 건너뜀")

    _log(f"대상 {len(tickers)}종목")
    latest_values = load_latest_values(conn)
    now = datetime.utcnow().isoformat()
    stats = {"ok": 0, "no_data": 0, "rate_limited": 0, "error": 0, "lt5": 0, "unchanged": 0}
    saved_rows = 0

    for n, t in enumerate(tickers, 1):
        df, status = fetch_quarterly(t)
        time.sleep(CALL_SLEEP)
        if df is None:
            stats[status] += 1
            continue
        quarters = extract_quarters(df)
        if not quarters:
            stats["no_data"] += 1
            continue
        to_save = changed_quarters(quarters, latest_values.get(t, {}))
        for (y, q), v in to_save.items():
            insert_quarter(conn, t, "US", y, q, v, "yfinance", "USD", now)
        if to_save:
            conn.commit()
            saved_rows += len(to_save)
        else:
            stats["unchanged"] += 1
        stats["ok"] += 1
        if len(quarters) < 5:
            stats["lt5"] += 1
        if n % 50 == 0:
            _log(f"  진행 {n}/{len(tickers)} {stats}")

    _log(f"완료 {stats} (lt5=최근 5분기 미만, unchanged=받았지만 바뀐 분기 없음) / 저장 {saved_rows}행")

    if args.tickers:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        from src.db.quarterly_financials import select_quarters
        for t in tickers:
            rows = select_quarters(conn, t, "US")
            if not rows:
                continue
            print(f"\n{t}  (단위: 백만 달러)")
            print(f"  {'분기':<10}{'매출':>14}{'영업이익':>14}{'순이익':>14}")
            for r in rows:
                def fmt(v):
                    return "-" if v is None else f"{v / 1e6:,.0f}"
                print(f"  {r['fiscal_year']}Q{r['fiscal_quarter']:<7}"
                      f"{fmt(r['revenue']):>14}{fmt(r['operating_income']):>14}"
                      f"{fmt(r['net_income']):>14}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
