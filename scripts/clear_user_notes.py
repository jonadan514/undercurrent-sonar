"""내 관찰 노트·회고·관심 종목 전부 지우기 (2026-11-21 사용자 요청, 일회성 정리).

지우는 표: observations, observation_reviews, my_watchlist, my_watchlist_note_history.
지우지 않는 것: 검토 기록(stock_decisions·stock_decision_outcomes, 사용자가 그대로 두기로 함), 지난 주간 브리핑에
이미 담긴 노트·회고(그 주 기록 - 원칙 5).
지우기 전에 행 전체를 JSON으로 로그에 찍는다(백업은 Actions 로그로 - 사용자 선택).

Usage:
  python scripts/clear_user_notes.py --dry-run
  python scripts/clear_user_notes.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.db.data_store import get_db  # noqa: E402

TABLES = ["observation_reviews", "observations", "my_watchlist_note_history", "my_watchlist"]


def _log(msg: str) -> None:
    print(f"[clear-notes] {msg}", flush=True)


def _columns(conn, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    conn = get_db()
    for t in TABLES:
        try:
            cols = _columns(conn, t)
            rows = conn.execute(f"SELECT * FROM {t}").fetchall()
        except Exception as e:  # 표가 없으면 지울 것도 없다
            _log(f"{t}: 읽기 실패({str(e)[:120]}) - 건너뜀")
            continue
        _log(f"{t}: {len(rows)}행")
        for r in rows:
            print("BACKUP|" + t + "|" + json.dumps(dict(zip(cols, r)) if cols else list(r), ensure_ascii=False), flush=True)
    if args.dry_run:
        _log("dry-run - 지우지 않음")
        return 0
    for t in TABLES:
        try:
            conn.execute(f"DELETE FROM {t}")
        except Exception as e:
            _log(f"{t}: 지우기 실패({str(e)[:120]})")
            return 1
    conn.commit()
    for t in TABLES:
        _log(f"{t}: 남은 행 {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
    _log("삭제 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
