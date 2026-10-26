"""signal_log의 신호가 4주·12주 뒤 어땠는지 signal_outcomes에 채운다 (2026-10-21, 사용자 결정: 신호 사후 확인).

규칙은 src/analyzers/signal_check.py. 성적표(compute_pick_returns.py)와 같은 방식:
- 시작가 = 신호 주차(월요일) 이후 첫 거래일 종가, 끝가 = 그 날짜 + 28·84일 이후 첫 거래일 종가(수정주가).
  실행일 막대는 쓰지 않는다(장중이면 종가가 아님, 2026-10-26).
- 지수(미국 SPY, 한국 ^KS11)도 같은 날짜로 재서 같이 적는다.
- 유니버스 기준(signal_universe_returns): 같은 유니버스 전체 종목의 같은 기간 수익률 중앙값 - 신호 종목이 중소형주라 지수와만 비교하면
  '중소형주 효과'가 섞여서(2026-10-21 첫 결과 확인 뒤 추가). 화면은 두 기준의 초과수익을 다 보여준다.
- 테마 신호는 그때 적어 둔 소속 기업 수익률의 중앙값(가격 있는 기업 3개 미만이면 데이터부족).
- 아직 기간이 안 지난 값은 NULL로 두고 다음 실행에서 채운다. 이미 채운 값은 덮어쓰지 않는다(COALESCE).

    python scripts/compute_signal_outcomes.py
"""
from __future__ import annotations

import csv
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.compute_pick_returns import _kr_yf_symbol, _load_kr_universe
from src.analyzers.signal_check import HORIZONS, completed_bars, distribution, fwd_return, median_return
from src.collectors.us_price_fetcher import USPriceFetcher
from src.db.data_store import get_db

BENCH = {"US": "SPY", "KR": "^KS11"}
COLS = [c for h in HORIZONS for c in (f"ret_{h}d", f"bench_{h}d")]
DDL = f"""
CREATE TABLE IF NOT EXISTS signal_outcomes (
  week      TEXT NOT NULL,
  kind      TEXT NOT NULL,
  market    TEXT NOT NULL,
  symbol    TEXT NOT NULL,
  {", ".join(f"{c} REAL" for c in COLS)},
  n_priced  INTEGER,            -- 테마: 가격이 있던 소속 기업 수
  updated_at TEXT NOT NULL,
  PRIMARY KEY (week, kind, market, symbol)
)
"""

# 유니버스 기준(2026-10-21): 신호 종목은 대부분 중소형주라 대형주 비중이 큰 지수와만 비교하면 '중소형주 효과'가 섞인다 -
# 같은 유니버스(미국 S&P 500·400, 한국 시총 3000억+) 전체 종목의 같은 기간 수익률 중앙값도 적어 둔다.
UNIV_DDL = f"""
CREATE TABLE IF NOT EXISTS signal_universe_returns (
  market     TEXT NOT NULL,
  week       TEXT NOT NULL,
  {", ".join(f"univ_{h}d REAL, n_{h}d INTEGER" for h in HORIZONS)},
  updated_at TEXT NOT NULL,
  PRIMARY KEY (market, week)
)
"""
UNIV_MIN_N = 50          # 가격이 있는 유니버스 종목이 이보다 적으면 기준을 비워 둔다(데이터부족)
US_LISTS = (ROOT / "data" / "sp500_list.csv", ROOT / "data" / "sp400_list.csv")


def _log(msg: str) -> None:
    print(f"[signal-outcomes] {msg}", flush=True)


def us_universe() -> list[str]:
    out: list[str] = []
    for path in US_LISTS:
        try:
            with path.open(encoding="utf-8") as f:
                out += [row["Symbol"].strip() for row in csv.DictReader(f) if row.get("Symbol")]
        except Exception:  # noqa: BLE001
            _log(f"{path.name} 없음 - 건너뜀")
    return sorted(set(out))


def main() -> int:
    today = date.today()
    conn = get_db()
    conn.execute(DDL)
    conn.execute(UNIV_DDL)
    try:
        rows = conn.execute("SELECT week, kind, market, symbol, detail FROM signal_log WHERE week <= ?",
                            ((today - timedelta(days=min(HORIZONS))).isoformat(),)).fetchall()
    except Exception as e:  # noqa: BLE001
        _log(f"signal_log 없음({type(e).__name__}) - 할 일 없음")
        return 0
    done = {tuple(r[:4]) for r in conn.execute(
        f"SELECT week, kind, market, symbol FROM signal_outcomes WHERE {' AND '.join(f'{c} IS NOT NULL' for c in COLS)}").fetchall()}
    todo = [r for r in rows if tuple(r[:4]) not in done]
    # 유니버스 기준(2026-10-21): 신호가 있는 (시장, 주차)마다 유니버스 전체 수익률 중앙값 - 아직 다 안 채운 것만
    univ_done = {tuple(r) for r in conn.execute(
        f"SELECT market, week FROM signal_universe_returns WHERE {' AND '.join(f'univ_{h}d IS NOT NULL' for h in HORIZONS)}").fetchall()}
    univ_todo = sorted({(r[2], r[0]) for r in rows} - univ_done)
    _log(f"기간이 지난 신호 {len(rows)}건 중 채울 것 {len(todo)}건, 유니버스 기준 채울 (시장, 주차) {len(univ_todo)}개")
    if not todo and not univ_todo:
        summarize(conn)
        return 0

    need: dict[str, set[str]] = {"US": set(), "KR": set()}
    for week, kind, market, symbol, detail in todo:
        if kind == "theme_busier":
            need[market] |= set(json.loads(detail).get("members", []))
        else:
            need[market].add(symbol)
    kr_universe = _load_kr_universe()
    universe = {"US": us_universe(), "KR": sorted(kr_universe)}
    for market in {m for m, _ in univ_todo}:
        need[market] |= set(universe[market])
    earliest = min([r[0] for r in todo] + [w for _, w in univ_todo])
    period = "2y" if (today - date.fromisoformat(earliest)).days > 300 else "1y"
    fetcher = USPriceFetcher()
    prices: dict[tuple[str, str], list[tuple[str, float]]] = {}

    def series(market: str, symbol: str) -> list[tuple[str, float]]:
        key = (market, symbol)
        if key not in prices:
            yf = symbol if symbol.startswith("^") or market == "US" else _kr_yf_symbol(symbol, kr_universe)
            df = fetcher.fetch_ohlcv(yf, period=period)
            # 오늘 막대(장중이면 종가가 아님)는 뺀다 - 2026-10-26
            prices[key] = [] if df is None or df.empty else completed_bars(
                [(d.strftime("%Y-%m-%d"), float(c)) for d, c in df["Close"].items()], today)
            time.sleep(0.2)
        return prices[key]

    for market, syms in need.items():
        if not syms:
            continue
        _log(f"{market}: 가격 조회 {len(syms)}종목 + 지수 {BENCH[market]}")
        series(market, BENCH[market])
        for i, s in enumerate(sorted(syms), 1):
            series(market, s)
            if i % 200 == 0:
                _log(f"  {i}/{len(syms)}")
    empty = sum(1 for v in prices.values() if not v)
    if empty:
        _log(f"가격을 못 받은 종목 {empty}/{len(prices)}개 - 그 종목은 빠진다")

    for market, week in univ_todo:
        vals, ns = {}, {}
        for h in HORIZONS:
            vals[h], ns[h] = median_return([fwd_return(series(market, s), week, h, today) for s in universe[market]],
                                           min_n=UNIV_MIN_N)
        conn.execute(
            "INSERT INTO signal_universe_returns (market, week, " + ", ".join(f"univ_{h}d, n_{h}d" for h in HORIZONS)
            + ", updated_at) VALUES (?, ?, " + ", ".join("?, ?" for _ in HORIZONS) + ", datetime('now')) "
            "ON CONFLICT(market, week) DO UPDATE SET "
            + ", ".join(f"univ_{h}d = COALESCE(signal_universe_returns.univ_{h}d, excluded.univ_{h}d), "
                        f"n_{h}d = COALESCE(signal_universe_returns.n_{h}d, excluded.n_{h}d)" for h in HORIZONS)
            + ", updated_at = datetime('now')",
            (market, week, *[x for h in HORIZONS for x in (vals[h], ns[h])]))
        _log(f"  유니버스 {market} {week}: " + ", ".join(
            f"{h}일 {'-' if vals[h] is None else f'{vals[h] * 100:+.1f}%'} (n={ns[h]})" for h in HORIZONS))

    filled = 0
    for week, kind, market, symbol, detail in todo:
        vals: dict[str, float | None] = {}
        n_priced = None
        for h in HORIZONS:
            if kind == "theme_busier":
                members = json.loads(detail).get("members", [])
                vals[f"ret_{h}d"], n_priced = median_return([fwd_return(series(market, m), week, h, today) for m in members])
            else:
                vals[f"ret_{h}d"] = fwd_return(series(market, symbol), week, h, today)
            vals[f"bench_{h}d"] = fwd_return(series(market, BENCH[market]), week, h, today)
        conn.execute(
            f"INSERT INTO signal_outcomes (week, kind, market, symbol, {', '.join(COLS)}, n_priced, updated_at) "
            f"VALUES (?, ?, ?, ?, {', '.join('?' for _ in COLS)}, ?, datetime('now')) "
            f"ON CONFLICT(week, kind, market, symbol) DO UPDATE SET "
            + ", ".join(f"{c} = COALESCE(signal_outcomes.{c}, excluded.{c})" for c in COLS)
            + ", n_priced = COALESCE(signal_outcomes.n_priced, excluded.n_priced), updated_at = datetime('now')",
            (week, kind, market, symbol, *[vals[c] for c in COLS], n_priced))
        filled += int(vals[f"ret_{HORIZONS[0]}d"] is not None)
    conn.commit()
    _log(f"완료 - {len(todo)}건 중 4주 결과 있는 것 {filled}건")
    summarize(conn)
    conn.close()
    return 0


def summarize(conn) -> None:
    """로그용 요약 - 성적표 화면(/api/data/signals)과 같은 묶음. 초과수익을 두 기준으로: 유니버스 중앙값 대비, 지수 대비."""
    univ = {(r[0], r[1]): r[2:] for r in conn.execute(
        "SELECT market, week, " + ", ".join(f"univ_{h}d" for h in HORIZONS) + " FROM signal_universe_returns").fetchall()}
    rows = conn.execute(
        "SELECT l.market, l.week, l.kind, l.detail, " + ", ".join(f"o.ret_{h}d, o.bench_{h}d" for h in HORIZONS) + " FROM signal_log l "
        "JOIN signal_outcomes o ON o.week = l.week AND o.kind = l.kind AND o.market = l.market AND o.symbol = l.symbol").fetchall()
    groups: dict[str, dict[tuple[str, int], list[float]]] = {}
    for r in rows:
        market, week, kind, detail = r[0], r[1], r[2], json.loads(r[3])
        name = f"{market} {kind}" + ({True: "·관심", False: "·관심 밖"}[bool(detail.get("watched"))] if kind == "insider_buy" else "")
        names = [name] + ([f"{market} theme_busier·축 조용"] if kind == "theme_busier" and detail.get("quiet_axes") else [])
        u = univ.get((market, week))
        for i, h in enumerate(HORIZONS):
            a, b = r[4 + 2 * i], r[5 + 2 * i]
            for n in names:
                g = groups.setdefault(n, {})
                if a is not None and b is not None:
                    g.setdefault(("지수", h), []).append(a - b)
                if a is not None and u and u[i] is not None:
                    g.setdefault(("유니버스", h), []).append(a - u[i])
    for name in sorted(groups):
        parts = []
        for base in ("유니버스", "지수"):
            for h in HORIZONS:
                d = distribution(groups[name].get((base, h), []))
                if d["n"]:
                    parts.append(f"{base} 대비 {h}일 n={d['n']} 중앙 {d['median'] * 100:+.1f}% ({d['q1'] * 100:+.1f}~{d['q3'] * 100:+.1f}%)")
        _log(f"  {name}: " + (" | ".join(parts) or "결과 없음"))


if __name__ == "__main__":
    raise SystemExit(main())
