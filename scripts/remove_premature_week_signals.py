"""아직 끝나지 않은 주에 미리 만들어진 theme_signals·theme_member_signals 행을 지운다 (정리용, 멱등).

화면은 MAX(week_start)를 '이번 주'로 읽어서, 정기 파이프라인보다 먼저 생긴 주 행이 있으면 레이더·테마 상세·기업 카드가
주가·라벨 없는 주를 보여 준다.
  - 2026-10-05: 정기 뉴스 수집이 밀려 월요일에 시작해 막 시작된 주를 채웠다(뉴스만 든 행) → signal_week_monday()로 규칙 수정.
  - 2026-11-05: 주 중간(목요일)에 실적 축 계산을 수동으로 돌려 11/2 주에 실적만 든 행이 생겼다 → compute_theme_earnings의
    기본 주를 고침(주 중간 수동 실행은 이미 있는 최신 주를 다시 쓴다).
11-05에 진단용 정리로 지웠던 것을 되살리며 실적만 든 행·소속 기업 행까지 다루게 했다.

안전장치:
  - 지정한 주가 아직 진행 중일 때만(정기 파이프라인이 채울 주보다 뒤) 지운다.
  - theme_signals는 주가 축과 라벨이 둘 다 빈 행만, theme_member_signals는 주가 수익률이 빈 행만 지운다
    (주가·라벨은 일요일 정기 파이프라인만 채운다 - 이 둘이 있으면 정기 실행이 만든 행이다).
  - theme_news(기사 원본)는 건드리지 않는다. 그 주는 일요일 정기 실행이 처음부터 다시 채운다.

Usage:
  python scripts/remove_premature_week_signals.py --week 2026-11-02 --dry-run
  python scripts/remove_premature_week_signals.py --week 2026-11-02
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.db.data_store import get_db
from src.db.theme_signals import signal_week_monday

PREMATURE = "price_arrow IS NULL AND label IS NULL"
PREMATURE_MEMBER = "price_ret IS NULL"


def _log(msg: str) -> None:
    print(f"[premature-week] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True, help="지울 주의 월요일 (YYYY-MM-DD)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    done = signal_week_monday(date.today()).isoformat()
    conn = get_db()
    latest_full = conn.execute(f"SELECT MAX(week_start) FROM theme_signals WHERE NOT ({PREMATURE})").fetchone()[0]
    if latest_full is not None and args.week <= latest_full:
        _log(f"{args.week}은 정기 실행이 채운 주({latest_full}) 이전이다 - 지우지 않는다")
        return 1
    _log(f"정기 실행이 채운 최신 주 {latest_full} · 오늘 기준 계산 주 {done}")

    rows = conn.execute(
        "SELECT market, theme_id, news_arrow, earn_arrow, price_arrow, label FROM theme_signals "
        "WHERE week_start = ? ORDER BY market, theme_id", (args.week,)).fetchall()
    drop = [r for r in rows if r[4] is None and r[5] is None]
    keep = [r for r in rows if not (r[4] is None and r[5] is None)]
    for m, tid, n, e, *_ in drop:
        _log(f"  삭제 대상 {m} {tid} news={n} earn={e}")
    for m, tid, n, e, p, lab in keep:
        _log(f"  유지(주가·라벨 있음) {m} {tid} news={n} earn={e} price={p} label={lab}")
    mem = conn.execute("SELECT COUNT(*), SUM(CASE WHEN price_ret IS NULL THEN 1 ELSE 0 END) FROM theme_member_signals "
                       "WHERE week_start = ?", (args.week,)).fetchone()
    _log(f"{args.week}: theme_signals 행 {len(rows)}개 중 삭제 {len(drop)} / 유지 {len(keep)} · "
         f"theme_member_signals 행 {mem[0]}개 중 삭제 {mem[1] or 0}")

    if args.dry_run:
        _log("dry-run - 바꾸지 않음")
        return 0
    conn.execute(f"DELETE FROM theme_signals WHERE week_start = ? AND {PREMATURE}", (args.week,))
    conn.execute(f"DELETE FROM theme_member_signals WHERE week_start = ? AND {PREMATURE_MEMBER}", (args.week,))
    conn.commit()
    left = conn.execute("SELECT COUNT(*) FROM theme_signals WHERE week_start = ?", (args.week,)).fetchone()[0]
    left_m = conn.execute("SELECT COUNT(*) FROM theme_member_signals WHERE week_start = ?", (args.week,)).fetchone()[0]
    _log(f"삭제 완료 - 남은 행 theme_signals {left} · theme_member_signals {left_m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
