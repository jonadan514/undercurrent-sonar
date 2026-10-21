"""그 주의 신호를 signal_log에 적는다 (2026-10-21, 사용자 결정: 신호 사후 확인). 규칙은 src/analyzers/signal_check.py.

매주 일요일 성적표 배치 앞에 돈다 - 주차 라벨은 브리핑과 같은 '다가오는 월요일'.
이력 표라 덮어쓰지 않는다(원칙 5): (주차, 종류, 시장, 종목)이 키, INSERT OR IGNORE.

지난 주도 원본 표(insider_trades·kr_disclosures·us_8k_filings·실적 반전 스냅샷)에서 다시 만들 수 있다(--backfill-weeks).
소급한 줄은 backfilled=1 - 그때의 '관심 표시'는 남아 있지 않아 지금 기준이고, 테마 소속도 지금 것이라 실제로 그 주에 본 신호와 다를 수 있다.
화면은 소급분을 따로 표시한다.

    python scripts/log_signals.py                      # 이번 주
    python scripts/log_signals.py --backfill-weeks 8   # 지난 8주도(소급)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.collect_insider_trades import targets
from scripts.compute_theme_events import events_for, members_by_theme
from src.analyzers.signal_check import insider_signals, theme_signals, turnaround_signals, week_window
from src.analyzers.theme_events import FETCH_DAYS, by_theme
from src.db.data_store import get_db

DDL = """
CREATE TABLE IF NOT EXISTS signal_log (
  week       TEXT NOT NULL,     -- 브리핑 주차(월요일). 결과는 이날 이후 첫 거래일 종가부터 잰다
  kind       TEXT NOT NULL,     -- insider_buy | turnaround_new | theme_busier
  market     TEXT NOT NULL,
  symbol     TEXT NOT NULL,     -- 종목코드, theme_busier는 테마 id
  detail     TEXT NOT NULL,     -- 그때의 값 JSON (관심 여부·산 사람 수·금액, 소속 기업 목록 등)
  backfilled INTEGER NOT NULL,  -- 1 = 나중에 원본 표에서 다시 만든 줄
  logged_at  TEXT NOT NULL,
  PRIMARY KEY (week, kind, market, symbol)
)
"""
MOVING = {"up2", "up1", "down"}


def _log(msg: str) -> None:
    print(f"[signals] {msg}", flush=True)


def upcoming_monday(now: datetime) -> str:
    return (now + timedelta(days=(7 - now.weekday()) % 7)).strftime("%Y-%m-%d")


def _rows(conn, sql: str, args: tuple) -> list[tuple]:
    try:
        return conn.execute(sql, args).fetchall()
    except Exception as e:  # noqa: BLE001 - 출처 표가 아직 없으면 그 신호만 건너뛴다
        _log(f"  조회 실패({type(e).__name__}) - 이 신호는 건너뜀: {sql[:60]}")
        return []


def week_signals(conn, week: str) -> list[dict]:
    start, end = week_window(week)
    out: list[dict] = []
    for market in ("US", "KR"):
        watched = {f"{market}:{s}" for s in targets(conn, market)}
        ins = [dict(zip(("market", "symbol", "owner", "value", "plan"), r)) for r in _rows(
            conn, "SELECT market, symbol, owner, value, plan FROM insider_trades WHERE market = ? AND filed_on BETWEEN ? AND ?",
            (market, start, end))]
        out += insider_signals(ins, watched)

        members = members_by_theme(conn, market)
        if members:
            sunday = date.fromisoformat(end)
            since = (sunday - timedelta(days=FETCH_DAYS)).isoformat()
            events, marks, coverage = events_for(conn, market, since)
            # 그 주 일요일 뒤의 공시는 빼야 '그때 본 것'이 된다
            events = [e for e in events if e["date"] <= end]
            marks = {k: [(t, d) for t, d in v if d <= end] for k, v in marks.items()}
            result = by_theme(members, events, sunday, marks, coverage)
            quiet = {}
            for theme_id, na, ea, pa in _rows(
                    conn, "SELECT theme_id, news_arrow, earn_arrow, price_arrow FROM theme_signals WHERE market = ? AND week_start = "
                          "(SELECT MAX(week_start) FROM theme_signals WHERE market = ? AND week_start <= ?)", (market, market, week)):
                quiet[theme_id] = not ({na, ea, pa} & MOVING)
            out += theme_signals(market, result, members, quiet)

    snaps = {r[0]: json.loads(r[1]) for r in _rows(conn, "SELECT week, payload FROM turnaround_weekly_snapshots WHERE week <= ? "
                                                         "ORDER BY week DESC LIMIT 2", (week,))}
    if week in snaps:
        prev = [v for k, v in snaps.items() if k < week]
        out += turnaround_signals(snaps[week], prev[0] if prev else None)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", default=None, help="주차(월요일, 기본: 다가오는 월요일)")
    ap.add_argument("--backfill-weeks", type=int, default=0, help="지난 몇 주도 원본 표에서 다시 만든다(backfilled=1)")
    args = ap.parse_args()

    this_week = args.week or upcoming_monday(datetime.now(timezone.utc))
    weeks = [(date.fromisoformat(this_week) - timedelta(weeks=i)).isoformat() for i in range(args.backfill_weeks, -1, -1)]
    conn = get_db()
    conn.execute(DDL)
    now = datetime.utcnow().isoformat(timespec="seconds")
    total = 0
    today = datetime.now(timezone.utc).date().isoformat()
    for week in weeks:
        # 그 주 공시 기간(월요일 전 7일)이 아직 안 끝났으면 적지 않는다 - 덜 모인 채 적히면 나중 공시가 INSERT OR IGNORE로 빠진다.
        # 정기 실행(일요일 23:00 UTC)은 기간 마지막 날이라 그날까지 모인 것을 적는다.
        if week_window(week)[1] > today:
            _log(f"{week}: 공시 기간이 아직 안 끝남 - 건너뜀")
            continue
        sigs = week_signals(conn, week)
        backfilled = int(week != this_week or bool(args.week))
        for s in sigs:
            conn.execute("INSERT OR IGNORE INTO signal_log (week, kind, market, symbol, detail, backfilled, logged_at) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (week, s["kind"], s["market"], s["symbol"], json.dumps(s["detail"], ensure_ascii=False), backfilled, now))
        conn.commit()
        kinds: dict[str, int] = {}
        for s in sigs:
            k = s["kind"] + ("(관심 밖)" if s["kind"] == "insider_buy" and not s["detail"]["watched"] else "")
            kinds[k] = kinds.get(k, 0) + 1
        _log(f"{week}{' (소급)' if backfilled else ''}: {len(sigs)}건 {kinds}")
        total += len(sigs)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
