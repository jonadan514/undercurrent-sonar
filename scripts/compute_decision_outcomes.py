"""검토 기록(stock_decisions)의 결과를 stock_decision_outcomes에 채운다(2026-11-15, 사용자: 3개월 가상 매수 검증).

- 시작가 = 기록한 날(한국 시간) '다음' 첫 거래일 종가. 기록할 때 본 가격은 그 전 종가라서 같은 날 종가를 쓰면 앞서 본 셈이 된다.
- 끝가 = 시작일 + 28·84·182일 이후 첫 거래일 종가(수정주가). 오늘 막대는 쓰지 않는다(장중이면 종가가 아님).
- 비교 기준: 그 시장 벤치마크(미국 SPY, 한국 코스피200 ^KS200). 종목과 기준이 같은 통화라 환율은 넣지 않는다.
  (첫 판은 TIGER 반도체TOP10·원화 기준이었는데 같은 날 사용자 결정으로 시장 벤치마크로 바꿨다 - 그 사이 쌓인 결과는 없다.
   표에 남은 ret_krw_*·semi_* 열은 비어 있는 채로 둔다.)
- 관심·보류·제외 모두 같은 방식으로 잰다('제외한 게 맞았나'도 보려고). 점수·적중률은 만들지 않는다(원칙 1) - 화면은 분포만.
- 이미 채운 값은 덮어쓰지 않는다(COALESCE). 끝 날짜가 지나고 RETRY_DAYS 동안만 다시 시도한다.

    python scripts/compute_decision_outcomes.py
"""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.compute_pick_returns import _kr_yf_symbol, _load_kr_universe  # noqa: E402
from src.analyzers.signal_check import completed_bars, fwd_return, price_on_or_after  # noqa: E402
from src.collectors.us_price_fetcher import USPriceFetcher  # noqa: E402
from src.db.turso_http import execute, execute_many, query  # noqa: E402

HORIZONS = (28, 84, 182)      # 4·12·26주(달력일)
RETRY_DAYS = 56
INDEX = {"US": "SPY", "KR": "^KS200"}   # 시장 벤치마크(S&P 500 ETF · 코스피200)
VALS = [c for h in HORIZONS for c in (f"ret_{h}d", f"mkt_{h}d")]
DDL = f"""CREATE TABLE IF NOT EXISTS stock_decision_outcomes (
  decision_id INTEGER PRIMARY KEY,
  market TEXT NOT NULL, symbol TEXT NOT NULL,
  entry_date TEXT, entry_price REAL,
  {", ".join(f"{c} REAL" for c in VALS)},
  updated_at TEXT NOT NULL
)"""


def _log(msg: str) -> None:
    print(msg, flush=True)


def entry_day(decided_on: str) -> str:
    """기록한 날 다음 날부터 첫 거래일을 찾는다."""
    return (date.fromisoformat(decided_on) + timedelta(days=1)).isoformat()


def outcome_values(entry: str, stock, index, today: date) -> dict:
    vals: dict[str, float | None] = {}
    for h in HORIZONS:
        vals[f"ret_{h}d"] = fwd_return(stock, entry, h, today)
        vals[f"mkt_{h}d"] = fwd_return(index, entry, h, today)
    return vals


def needs_work(decided_on: str, done: dict | None, today: date) -> bool:
    entry = entry_day(decided_on)
    if done is None or done.get("entry_price") is None:
        return True
    for h in HORIZONS:
        end = date.fromisoformat(entry) + timedelta(days=h)
        if end <= today <= end + timedelta(days=RETRY_DAYS) and done.get(f"ret_{h}d") is None:
            return True
    return False


def main() -> int:
    today = date.today()
    execute(DDL)
    try:
        decisions = query("SELECT id, decided_on, market, symbol FROM stock_decisions")
    except Exception as e:  # noqa: BLE001
        _log(f"검토 기록 없음({type(e).__name__}) - 할 일 없음")
        return 0
    done = {int(r["decision_id"]): r for r in query(f"SELECT decision_id, entry_price, {', '.join(VALS)} FROM stock_decision_outcomes")}
    todo = [d for d in decisions if needs_work(d["decided_on"], done.get(int(d["id"])), today)]
    _log(f"검토 기록 {len(decisions)}건 중 채울 것 {len(todo)}건")
    if not todo:
        return 0

    kr_universe = _load_kr_universe()
    fetcher = USPriceFetcher()
    cache: dict[str, list[tuple[str, float]]] = {}

    def series(yf_sym: str) -> list[tuple[str, float]]:
        if yf_sym not in cache:
            df = fetcher.fetch_ohlcv(yf_sym, period="2y")
            cache[yf_sym] = [] if df is None or df.empty else completed_bars(
                [(d.strftime("%Y-%m-%d"), float(c)) for d, c in df["Close"].items()], today)
            time.sleep(0.2)
        return cache[yf_sym]

    stmts = []
    for d in todo:
        m, s = d["market"], str(d["symbol"])
        yf_sym = s.replace(".", "-") if m == "US" else _kr_yf_symbol(s, kr_universe)
        stock = series(yf_sym)
        entry = entry_day(d["decided_on"])
        first = price_on_or_after(stock, entry)
        vals = outcome_values(entry, stock, series(INDEX[m]), today)
        cols = ["entry_date", "entry_price", *VALS]
        row = [first[0] if first else None, first[1] if first else None, *[vals[c] for c in VALS]]
        stmts.append((
            f"INSERT INTO stock_decision_outcomes (decision_id, market, symbol, {', '.join(cols)}, updated_at) "
            f"VALUES (?, ?, ?, {', '.join('?' for _ in cols)}, datetime('now')) ON CONFLICT(decision_id) DO UPDATE SET "
            + ", ".join(f"{c} = COALESCE(stock_decision_outcomes.{c}, excluded.{c})" for c in cols)
            + ", updated_at = datetime('now')",
            [int(d["id"]), m, s, *row]))
        rets = [vals[f"ret_{h}d"] for h in HORIZONS]
        _log(f"  #{d['id']} {m}:{s} {d['decided_on']} → 시작 {row[0] or '대기'} · "
             + " · ".join(f"{h}일 " + ("-" if r is None else f"{r * 100:+.1f}%") for h, r in zip(HORIZONS, rets)))
    for i in range(0, len(stmts), 100):
        execute_many(stmts[i:i + 100])
    _log(f"완료 - {len(stmts)}건 기록")
    return 0


if __name__ == "__main__":
    sys.exit(main())
