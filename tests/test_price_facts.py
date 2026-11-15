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
