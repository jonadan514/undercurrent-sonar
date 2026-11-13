"""한국 실적 발표일 - 작년 잠정실적 날짜를 52주 뒤로(2026-11-13)."""
from datetime import date

from src.collectors.earnings_calendar import project_from_last_year


def test_projects_next_quarter_same_weekday():
    hist = ["2025-10-28", "2026-01-29", "2026-04-28", "2026-07-28", "2026-10-27"]
    p = project_from_last_year(hist, date(2026, 11, 13))
    assert p == date(2027, 1, 28) and p.weekday() == date(2026, 1, 29).weekday()


def test_skips_quarter_already_reported_earlier_this_year():
    # 작년엔 11/14에 냈는데 올해는 10/30에 이미 냄 -> 11/13 예상을 만들지 않는다
    assert project_from_last_year(["2025-11-14", "2026-10-30"], date(2026, 11, 10)) is None


def test_no_history_or_too_far():
    assert project_from_last_year([], date(2026, 11, 13)) is None
    assert project_from_last_year(["2026-04-28"], date(2026, 11, 13)) is None   # 2027-04-27은 120일 밖
