"""다음 실적 발표일 파싱 (src/collectors/earnings_calendar.py)."""
from datetime import date, datetime, timezone

from src.collectors.earnings_calendar import parse_info


def _ts(y, m, d, h=0):
    return int(datetime(y, m, d, h, tzinfo=timezone.utc).timestamp())


def test_confirmed_after_close_keeps_us_date():
    # 미국 장 마감 후 20:05 ET = 다음날 00:05 UTC -> 뉴욕 날짜 그대로
    info = {"earningsTimestampStart": _ts(2026, 10, 22, 0) + 300, "earningsTimestampEnd": _ts(2026, 10, 22, 0) + 300,
            "isEarningsDateEstimate": False}
    assert parse_info(info, "US", date(2026, 10, 17)) == {
        "earnings_date": "2026-10-21", "earnings_date_end": "2026-10-21", "is_estimate": 0}


def test_estimate_range_and_past():
    info = {"earningsTimestampStart": _ts(2026, 10, 27, 3), "earningsTimestampEnd": _ts(2026, 10, 31, 3)}
    rec = parse_info(info, "KR", date(2026, 10, 17))
    assert rec["earnings_date"] == "2026-10-27" and rec["earnings_date_end"] == "2026-10-31" and rec["is_estimate"] == 1
    assert parse_info({"earningsTimestampStart": _ts(2026, 7, 30, 3)}, "KR", date(2026, 10, 17)) is None
    assert parse_info({}, "US", date(2026, 10, 17)) is None and parse_info(None, "US", date(2026, 10, 17)) is None
