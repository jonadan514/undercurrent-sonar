"""실적 축 기본 주(2026-11-05) - 주 중간 수동 실행이 진행 중인 주를 새로 열지 않는다."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from compute_theme_earnings import default_week  # noqa: E402


class _Conn:
    def __init__(self, latest):
        self.latest = latest

    def execute(self, sql, *a):
        return self

    def fetchone(self):
        return (self.latest,)


def test_midweek_reuses_latest_existing_week():
    assert default_week(_Conn("2026-10-26"), date(2026, 11, 5)) == "2026-10-26"   # 목요일


def test_scheduled_days_open_just_finished_week():
    assert default_week(_Conn("2026-10-19"), date(2026, 11, 1)) == "2026-10-26"   # 일요일 정기
    assert default_week(_Conn("2026-10-19"), date(2026, 11, 2)) == "2026-10-26"   # 월요일로 밀린 정기


def test_midweek_when_week_already_exists():
    assert default_week(_Conn("2026-11-02"), date(2026, 11, 5)) == "2026-11-02"
