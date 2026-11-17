from datetime import date, timedelta

from src.analyzers.price_facts import completed, price_facts


def _series(closes, start=date(2025, 1, 1)):
    return [((start + timedelta(days=i)).isoformat(), c) for i, c in enumerate(closes)]


def test_too_short_is_none():
    assert price_facts(_series([10.0] * 63)) is None


def test_basic_facts_without_ma200():
    closes = [10.0] * 40 + [20.0] * 24          # 64 bars
    f = price_facts(_series(closes))
    assert f["close"] == 20.0
    assert f["high_52w"] == 20.0 and f["low_52w"] == 10.0
    assert f["pos_52w"] == 1.0
    assert f["from_high"] == 0.0
    assert abs(f["ret_3m"] - 1.0) < 1e-9        # 63 bars ago was 10
    assert f["ret_1m"] == 0.0
    assert f["ma200"] is None and f["above_ma200"] is None and f["ma200_slope"] is None


def test_ma200_and_slope():
    closes = [float(i) for i in range(1, 241)]   # 240 bars rising
    f = price_facts(_series(closes))
    assert f["above_ma200"] == 1
    assert f["ma200_slope"] > 0
    assert abs(f["ma200"] - sum(range(41, 241)) / 200) < 1e-9


def test_flat_range_has_no_position():
    f = price_facts(_series([5.0] * 70))
    assert f["pos_52w"] is None


def test_completed_drops_today_and_bad_values():
    s = [("2026-11-13", 1.0), ("2026-11-14", None), ("2026-11-15", 2.0)]
    assert completed(s, date(2026, 11, 15)) == [("2026-11-13", 1.0)]


def test_last_us_close_and_fresh():
    from datetime import datetime, timezone
    from scripts.compute_price_facts import is_fresh, last_us_close
    mon_night = datetime(2026, 11, 16, 23, 0, tzinfo=timezone.utc)      # 월 23:00 UTC - 월 종가 있음
    tue_morning = datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc)
    sat = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
    mon_early = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)      # 월 장 전 - 금요일
    assert str(last_us_close(mon_night)) == "2026-11-16"
    assert str(last_us_close(tue_morning)) == "2026-11-16"
    assert str(last_us_close(sat)) == "2026-11-20"
    assert str(last_us_close(mon_early)) == "2026-11-13"
    assert is_fresh(tue_morning, "2026-11-16", None)
    assert not is_fresh(tue_morning, "2026-11-13", "2026-11-16 12:00:00")       # 오래 전에 돎 - 다시
    assert is_fresh(tue_morning, "2026-11-13", "2026-11-16 22:30:00")           # 방금 돌았는데 종가 없음(휴장 등) - 기다림
    assert not is_fresh(tue_morning, None, None)
