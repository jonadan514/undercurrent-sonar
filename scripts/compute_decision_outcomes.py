"""검토 기록(stock_decisions)의 결과를 stock_decision_outcomes에 채운다(2026-11-15, 사용자: 3개월 가상 매수 검증).

- 시작가 = 기록한 날(한국 시간) '다음' 첫 거래일 종가. 기록할 때 본 가격은 그 전 종가라서 같은 날 종가를 쓰면 앞서 본 셈이 된다.
- 끝가 = 시작일 + 28·84·182일 이후 첫 거래일 종가(수정주가). 오늘 막대는 쓰지 않는다(장중이면 종가가 아님).
- 비교 기준: TIGER 반도체TOP10(396500, 사용자가 실제로 들고 있는 것 - 원화)과 그 시장 지수(미국 SPY, 한국 코스피).
- 미국 종목은 원화 기준 수익률도 적는다(달러 수익률 x 원/달러 변화) - TIGER와 같은 돈 기준으로 비교하려고.
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
SEMI = "396500.KS"            # TIGER 반도체TOP10
INDEX = {"US": "SPY", "KR": "^KS11"}
FX = "KRW=X"                  # 원/달러
VALS = [c for h in HORIZONS for c in (f"ret_{h}d", f"ret_krw_{h}d", f"semi_{h}d", f"mkt_{h}d")]
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


def krw_return(ret: float | None, fx: float | None) -> float | None:
    if ret is None or fx is None:
        return None
    return (1 + ret) * (1 + fx) - 1


def outcome_values(market: str, entry: str, stock, semi, index, fx, today: date) -> dict:
    vals: dict[str, float | None] = {}
    for h in HORIZONS:
        r = fwd_return(stock, entry, h, today)
        vals[f"ret_{h}d"] = r
        vals[f"ret_krw_{h}d"] = r if market == "KR" else krw_return(r, fwd_return(fx, entry, h, today))
        vals[f"semi_{h}d"] = fwd_return(semi, entry, h, today)
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
        vals = outcome_values(m, entry, stock, series(SEMI), series(INDEX[m]), series(FX) if m == "US" else [], today)
        cols = ["entry_date", "entry_price", *VALS]
        row = [first[0] if first else None, first[1] if first else None, *[vals[c] for c in VALS]]
        stmts.append((
            f"INSERT INTO stock_decision_outcomes (decision_id, market, symbol, {', '.join(cols)}, updated_at) "
            f"VALUES (?, ?, ?, {', '.join('?' for _ in cols)}, datetime('now')) ON CONFLICT(decision_id) DO UPDATE SET "
            + ", ".join(f"{c} = COALESCE(stock_decision_outcomes.{c}, excluded.{c})" for c in cols)
            + ", updated_at = datetime('now')",
            [int(d["id"]), m, s, *row]))
        rets = [vals[f"ret_krw_{h}d"] for h in HORIZONS]
        _log(f"  #{d['id']} {m}:{s} {d['decided_on']} → 시작 {row[0] or '대기'} · "
             + " · ".join(f"{h}일 " + ("-" if r is None else f"{r * 100:+.1f}%") for h, r in zip(HORIZONS, rets)))
    for i in range(0, len(stmts), 100):
        execute_many(stmts[i:i + 100])
    _log(f"완료 - {len(stmts)}건 기록")
    return 0


if __name__ == "__main__":
    sys.exit(main())
