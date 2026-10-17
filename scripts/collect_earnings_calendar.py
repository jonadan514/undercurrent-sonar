"""워치리스트·내 관심·관찰 노트 종목의 다음 실적 발표일을 earnings_calendar에 쌓는다 (2026-10-17).

주간 브리핑 "이번 주 실적 발표"용 - 일요일 밤 브리핑 직전에 돈다. 규칙은 src/collectors/earnings_calendar.py.
이력 표라 덮어쓰지 않는다(원칙 5): (ticker, market, fetched_on) 하루 한 행, 같은 날 재실행은 무시.
읽는 쪽은 종목별 가장 최근 수집 행을 쓴다.

    python scripts/collect_earnings_calendar.py                      # 전체 대상
    python scripts/collect_earnings_calendar.py --tickers MU 005930  # 몇 종목 확인(저장 안 함, 표 출력)
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import yfinance as yf

from src.collectors.earnings_calendar import parse_info
from src.collectors.kr_kospi_list import yf_suffix as kr_yf_suffix
from src.db.data_store import get_db

SLEEP_SEC = 0.3
SOURCE = "yfinance"

EARNINGS_CALENDAR_DDL = """
CREATE TABLE IF NOT EXISTS earnings_calendar (
  ticker            TEXT NOT NULL,
  market            TEXT NOT NULL,
  fetched_on        TEXT NOT NULL,   -- 수집일 'YYYY-MM-DD'
  earnings_date     TEXT NOT NULL,   -- 발표일(예상이면 범위 시작)
  earnings_date_end TEXT NOT NULL,   -- 범위 끝(공지된 날짜면 같은 날)
  is_estimate       INTEGER NOT NULL,-- 1 = 회사 공지 전 예상치
  source            TEXT NOT NULL,
  fetched_at        TEXT NOT NULL,
  PRIMARY KEY (ticker, market, fetched_on)
)
"""


def _log(msg: str) -> None:
    print(f"[earn-cal] {msg}", flush=True)


def yf_symbols(ticker: str, market: str) -> list[str]:
    if market != "KR":
        return [ticker.replace(".", "-")]
    primary = f"{ticker}{kr_yf_suffix(ticker)}"
    return [primary, f"{ticker}.KQ" if primary.endswith(".KS") else f"{ticker}.KS"]


def targets(conn) -> list[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for sql in ("SELECT symbol, market FROM watchlist_candidates",
                "SELECT symbol, market FROM my_watchlist",
                "SELECT DISTINCT ticker, market FROM observations WHERE kind = 'stock' AND ticker IS NOT NULL"):
        try:
            out.update((r[0], r[1]) for r in conn.execute(sql).fetchall() if r[0] and r[1] in ("US", "KR"))
        except Exception as e:  # noqa: BLE001 - 표가 없으면 그 출처만 건너뛴다
            _log(f"대상 조회 실패({type(e).__name__}) - 건너뜀")
    return sorted(out, key=lambda x: (x[1], x[0]))


def fetch(ticker: str, market: str, today: date) -> dict | None:
    for sym in yf_symbols(ticker, market):
        try:
            info = yf.Ticker(sym).info
        except Exception:  # noqa: BLE001
            info = None
        finally:
            time.sleep(SLEEP_SEC)
        rec = parse_info(info, market, today)
        if rec:
            return rec
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", default=None, help="몇 종목만 확인(저장 안 함). 6자리 숫자면 KR")
    args = ap.parse_args()

    today = date.today()
    now = datetime.utcnow().isoformat()
    if args.tickers:
        for t in args.tickers:
            m = "KR" if t.isdigit() else "US"
            print(f"{m} {t}: {fetch(t, m, today)}")
        return 0

    conn = get_db()
    conn.execute(EARNINGS_CALENDAR_DDL)
    conn.commit()
    tg = targets(conn)
    _log(f"대상 {len(tg)}종목")
    stats = {"US": [0, 0], "KR": [0, 0]}   # [조회, 날짜 있음]
    for n, (t, m) in enumerate(tg, 1):
        stats[m][0] += 1
        rec = fetch(t, m, today)
        if rec:
            stats[m][1] += 1
            conn.execute(
                "INSERT OR IGNORE INTO earnings_calendar (ticker, market, fetched_on, earnings_date, earnings_date_end, "
                "is_estimate, source, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (t, m, today.isoformat(), rec["earnings_date"], rec["earnings_date_end"], rec["is_estimate"], SOURCE, now))
        if n % 50 == 0:
            conn.commit()
            _log(f"  진행 {n}/{len(tg)} {stats}")
    conn.commit()
    conn.close()
    _log("완료 " + " / ".join(f"{m} {a}종목 중 날짜 {b}" for m, (a, b) in stats.items()))
    attempted = sum(a for a, _ in stats.values())
    if attempted >= 20 and sum(b for _, b in stats.values()) == 0:
        _log("날짜 0종목 - 실패로 끝낸다")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
