"""theme_events 저장량 줄이기(2026-10-25) - 이력엔 주마다 첫 실행만 목록을 남긴다."""
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from compute_theme_events import DDL, keep_items_this_run  # noqa: E402


def _conn():
    c = sqlite3.connect(":memory:")
    c.execute(DDL)
    return c


def test_first_run_of_week_keeps_items():
    c = _conn()
    assert keep_items_this_run(c, "US", date(2026, 10, 28))   # 수요일, 이번 주 기록 없음


def test_later_run_same_week_skips_items():
    c = _conn()
    c.execute("INSERT INTO theme_events VALUES ('US', 'ai', '2026-10-26T14:00:00', '{}', '[1]')")
    assert not keep_items_this_run(c, "US", date(2026, 10, 28))
    assert keep_items_this_run(c, "KR", date(2026, 10, 28))   # 시장별로 따로


def test_counts_only_rows_do_not_count_as_kept():
    c = _conn()
    c.execute("INSERT INTO theme_events VALUES ('US', 'ai', '2026-10-26T14:00:00', '{}', '')")
    assert keep_items_this_run(c, "US", date(2026, 10, 28))


def test_last_week_rows_do_not_block_new_week():
    c = _conn()
    c.execute("INSERT INTO theme_events VALUES ('US', 'ai', '2026-10-25T14:00:00', '{}', '[1]')")   # 지난 주 일요일
    assert keep_items_this_run(c, "US", date(2026, 10, 26))   # 월요일
