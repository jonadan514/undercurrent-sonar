"""차트 상태 사실을 매일 stock_price_facts에 채운다(2026-11-15, 사용자: 밸류·실적·차트 중 차트만 툴 밖에서 봐야 했다).

대상: 유니버스(미국 S&P 500·400, 한국 시총 3000억+) + 내 관심 종목 + 검토 기록에 있는 종목(유니버스 밖 블로그 종목 포함)
     + 시장 벤치마크(SPY, KODEX 200 - 코스피200 추종 ETF).
계산은 src/analyzers/price_facts.py - 52주 위치, 200일선 위/아래·기울기, 1·3개월 수익률. 판정·점수 없음(원칙 1).
이 표는 종목마다 '지금 값' 한 줄(캐시)이다 - 이력이 아니라 덮어쓴다. 그때 값은 검토 기록 snapshot에 따로 남는다.

    python scripts/compute_price_facts.py            # 전부
    python scripts/compute_price_facts.py --only-extra   # 관심·검토 기록·기준만(빠른 확인)
    python scripts/compute_price_facts.py --if-stale     # 마지막 미국 장 마감 뒤 값이 이미 있으면 건너뜀(이어 도는 수집에서 매 차례 부른다)
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yfinance as yf  # noqa: E402
from yfinance.exceptions import YFRateLimitError  # noqa: E402

from scripts.compute_pick_returns import _kr_yf_symbol, _load_kr_universe  # noqa: E402
from scripts.compute_signal_outcomes import us_universe  # noqa: E402
from src.analyzers.price_facts import completed, price_facts  # noqa: E402
from src.db.turso_http import execute, execute_many, query  # noqa: E402

BENCH = [("US", "SPY"), ("KR", "069500")]   # 시장 벤치마크 - S&P 500 ETF · KODEX 200(코스피200 추종)
LOOKBACK_DAYS = 400       # 52주(252거래일) + 200일선 기울기(20거래일) 여유
BATCH = 100
BACKOFF = [60, 180]
COLS = ["as_of", "close", "high_52w", "low_52w", "pos_52w", "from_high", "range_days", "ret_1m", "ret_3m",
        "ma200", "above_ma200", "ma200_slope"]
DDL = f"""CREATE TABLE IF NOT EXISTS stock_price_facts (
  market TEXT NOT NULL, symbol TEXT NOT NULL,
  as_of TEXT, close REAL, high_52w REAL, low_52w REAL, pos_52w REAL, from_high REAL, range_days INTEGER,
  ret_1m REAL, ret_3m REAL, ma200 REAL, above_ma200 INTEGER, ma200_slope REAL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (market, symbol)
)"""


US_CLOSE_UTC = (21, 30)   # 미국 장 마감(21:00 UTC, 서머타임이면 20:00) + 여유 - 이 시각이 지나야 그날 종가가 있다고 본다
RETRY_HOURS = 6           # 기대한 날짜 종가가 없어도(휴장일 등) 이 시간 안에 이미 돌았으면 다시 받지 않는다


def last_us_close(now: datetime) -> date:
    """now(UTC) 기준 가장 최근에 마감한 미국 평일. 휴장일은 모른다 - RETRY_HOURS가 막는다."""
    d = now.date()
    if (now.hour, now.minute) < US_CLOSE_UTC:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def is_fresh(now: datetime, spy_as_of: str | None, updated_at: str | None) -> bool:
    """SPY 값이 마지막 미국 장 마감일 것이면 최신. 아니어도 RETRY_HOURS 안에 돌았으면 최신으로 친다(휴장일에 계속 다시 받지 않게)."""
    if spy_as_of and spy_as_of >= last_us_close(now).isoformat():
        return True
    if updated_at:
        try:
            ran = datetime.fromisoformat(str(updated_at).replace(" ", "T")).replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        return now - ran < timedelta(hours=RETRY_HOURS)
    return False


def _log(msg: str) -> None:
    print(msg, flush=True)


def extra_targets() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set(BENCH)
    for sql in ("SELECT market, symbol FROM my_watchlist", "SELECT market, symbol FROM stock_decisions"):
        try:
            out |= {(r["market"], str(r["symbol"]).upper()) for r in query(sql)}
        except Exception as e:  # noqa: BLE001 - 표가 아직 없을 수 있다
            _log(f"  {sql.split('FROM')[1].strip()} 읽기 건너뜀({type(e).__name__})")
    return out


def yf_symbol(market: str, symbol: str, kr_universe: dict[str, str]) -> str:
    if symbol.startswith("^"):
        return symbol
    if market == "US":
        return symbol.replace(".", "-")        # BRK.B -> BRK-B
    return _kr_yf_symbol(symbol, kr_universe)


def download(tickers: list[str], start: str) -> dict[str, list[tuple[str, float]]]:
    out: dict[str, list[tuple[str, float]]] = {}
    for i in range(0, len(tickers), BATCH):
        chunk = tickers[i:i + BATCH]
        df = None
        for attempt in range(len(BACKOFF) + 1):
            try:
                df = yf.download(chunk, start=start, progress=False, group_by="ticker", threads=True, auto_adjust=True)
                break
            except YFRateLimitError:
                if attempt == len(BACKOFF):
                    _log("  요청 제한 - 남은 묶음은 다음 실행에서")
                    return out
                time.sleep(BACKOFF[attempt])
            except Exception as e:  # noqa: BLE001
                _log(f"  묶음 조회 실패({type(e).__name__}) - 건너뜀")
                break
        if df is None or df.empty:
            continue
        for t in chunk:
            try:
                s = df[t]["Close"].dropna()
            except (KeyError, TypeError):
                continue
            out[t] = [(d.strftime("%Y-%m-%d"), float(c)) for d, c in s.items()]
        _log(f"  {min(i + BATCH, len(tickers))}/{len(tickers)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-extra", action="store_true")
    ap.add_argument("--if-stale", action="store_true")
    args = ap.parse_args()
    today = date.today()
    execute(DDL)
    if args.if_stale:
        r = query("SELECT as_of, updated_at FROM stock_price_facts WHERE market = 'US' AND symbol = 'SPY'")
        if is_fresh(datetime.now(timezone.utc), r[0]["as_of"] if r else None, r[0]["updated_at"] if r else None):
            _log(f"차트 상태 최신(SPY {r[0]['as_of'] if r else '-'}) - 건너뜀")
            return 0

    kr_universe = _load_kr_universe()
    targets = extra_targets()
    if not args.only_extra:
        targets |= {("US", s) for s in us_universe()} | {("KR", s) for s in kr_universe}
    by_yf = {yf_symbol(m, s, kr_universe): (m, s) for m, s in sorted(targets)}
    _log(f"대상 {len(by_yf)}종목(미국 {sum(1 for m, _ in by_yf.values() if m == 'US')}, 한국 {sum(1 for m, _ in by_yf.values() if m == 'KR')})")

    series = download(sorted(by_yf), (today - timedelta(days=LOOKBACK_DAYS)).isoformat())
    stmts, short = [], []
    for t, (m, s) in by_yf.items():
        f = price_facts(completed(series.get(t, []), today))
        if not f:
            short.append(t)
            continue
        stmts.append((
            f"INSERT INTO stock_price_facts (market, symbol, {', '.join(COLS)}, updated_at) "
            f"VALUES (?, ?, {', '.join('?' for _ in COLS)}, datetime('now')) "
            f"ON CONFLICT(market, symbol) DO UPDATE SET "
            + ", ".join(f"{c} = excluded.{c}" for c in COLS) + ", updated_at = datetime('now')",
            [m, s, *[f[c] for c in COLS]]))
    for i in range(0, len(stmts), 200):
        execute_many(stmts[i:i + 200])
    _log(f"완료 - 저장 {len(stmts)}종목, 기록 부족·조회 실패 {len(short)}종목(데이터 부족으로 비워 둠): {', '.join(short[:20])}")
    for m, s in BENCH:
        r = query("SELECT as_of, close, pos_52w, above_ma200, ret_3m FROM stock_price_facts WHERE market = ? AND symbol = ?", [m, s])
        _log(f"  기준 {s}: {r[0] if r else '없음'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
