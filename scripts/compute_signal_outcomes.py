"""signal_log의 신호가 4주·12주 뒤 어땠는지 signal_outcomes에 채운다 (2026-10-21, 사용자 결정: 신호 사후 확인).

규칙은 src/analyzers/signal_check.py. 성적표(compute_pick_returns.py)와 같은 방식:
- 시작가 = 신호 주차(월요일) 이후 첫 거래일 종가, 끝가 = 그 날짜 + 28·84일 이후 첫 거래일 종가(수정주가).
- 지수(미국 SPY, 한국 ^KS11)도 같은 날짜로 재서 같이 적는다 - 화면은 초과수익(신호 - 지수)으로 본다.
- 테마 신호는 그때 적어 둔 소속 기업 수익률의 중앙값(가격 있는 기업 3개 미만이면 데이터부족).
- 아직 기간이 안 지난 값은 NULL로 두고 다음 실행에서 채운다. 이미 채운 값은 덮어쓰지 않는다(COALESCE).

    python scripts/compute_signal_outcomes.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.compute_pick_returns import _kr_yf_symbol, _load_kr_universe
from src.analyzers.signal_check import HORIZONS, distribution, fwd_return, median_return
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


def _log(msg: str) -> None:
    print(f"[signal-outcomes] {msg}", flush=True)


def main() -> int:
    today = date.today()
    conn = get_db()
    conn.execute(DDL)
    try:
        rows = conn.execute("SELECT week, kind, market, symbol, detail FROM signal_log WHERE week <= ?",
                            ((today - timedelta(days=min(HORIZONS))).isoformat(),)).fetchall()
    except Exception as e:  # noqa: BLE001
        _log(f"signal_log 없음({type(e).__name__}) - 할 일 없음")
        return 0
    done = {tuple(r[:4]) for r in conn.execute(
        f"SELECT week, kind, market, symbol FROM signal_outcomes WHERE {' AND '.join(f'{c} IS NOT NULL' for c in COLS)}").fetchall()}
    todo = [r for r in rows if tuple(r[:4]) not in done]
    _log(f"기간이 지난 신호 {len(rows)}건 중 채울 것 {len(todo)}건")
    if not todo:
        summarize(conn)
        return 0

    need: dict[str, set[str]] = {"US": set(), "KR": set()}
    for week, kind, market, symbol, detail in todo:
        if kind == "theme_busier":
            need[market] |= set(json.loads(detail).get("members", []))
        else:
            need[market].add(symbol)
    earliest = min(r[0] for r in todo)
    period = "2y" if (today - date.fromisoformat(earliest)).days > 300 else "1y"
    kr_universe = _load_kr_universe()
    fetcher = USPriceFetcher()
    prices: dict[tuple[str, str], list[tuple[str, float]]] = {}

    def series(market: str, symbol: str) -> list[tuple[str, float]]:
        key = (market, symbol)
        if key not in prices:
            yf = symbol if symbol.startswith("^") or market == "US" else _kr_yf_symbol(symbol, kr_universe)
            df = fetcher.fetch_ohlcv(yf, period=period)
            prices[key] = [] if df is None or df.empty else [(d.strftime("%Y-%m-%d"), float(c)) for d, c in df["Close"].items()]
            time.sleep(0.2)
        return prices[key]

    for market, syms in need.items():
        _log(f"{market}: 가격 조회 {len(syms)}종목 + 지수 {BENCH[market]}")
        series(market, BENCH[market])
        for i, s in enumerate(sorted(syms), 1):
            series(market, s)
            if i % 100 == 0:
                _log(f"  {i}/{len(syms)}")
    empty = sum(1 for v in prices.values() if not v)
    if empty:
        _log(f"가격을 못 받은 종목 {empty}/{len(prices)}개 - 그 신호는 NULL로 남는다")

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
    """로그용 요약 - 성적표 화면(/api/data/signals)과 같은 묶음, 초과수익(신호 - 지수) 분포."""
    rows = conn.execute(
        "SELECT l.market, l.kind, l.detail, " + ", ".join(f"o.ret_{h}d, o.bench_{h}d" for h in HORIZONS) + " FROM signal_log l "
        "JOIN signal_outcomes o ON o.week = l.week AND o.kind = l.kind AND o.market = l.market AND o.symbol = l.symbol").fetchall()
    groups: dict[str, dict[int, list[float]]] = {}
    for r in rows:
        market, kind, detail = r[0], r[1], json.loads(r[2])
        name = f"{market} {kind}" + ({True: "·관심", False: "·관심 밖"}[bool(detail.get("watched"))] if kind == "insider_buy" else "")
        names = [name] + ([f"{market} theme_busier·축 조용"] if kind == "theme_busier" and detail.get("quiet_axes") else [])
        for i, h in enumerate(HORIZONS):
            a, b = r[3 + 2 * i], r[4 + 2 * i]
            if a is not None and b is not None:
                for n in names:
                    groups.setdefault(n, {}).setdefault(h, []).append(a - b)
    for name in sorted(groups):
        parts = []
        for h in HORIZONS:
            d = distribution(groups[name].get(h, []))
            parts.append(f"{h}일 n={d['n']}" + ("" if not d["n"] else
                         f" 중앙 {d['median'] * 100:+.1f}% ({d['q1'] * 100:+.1f}~{d['q3'] * 100:+.1f}%)"))
        _log(f"  {name}: " + " | ".join(parts))


if __name__ == "__main__":
    raise SystemExit(main())
