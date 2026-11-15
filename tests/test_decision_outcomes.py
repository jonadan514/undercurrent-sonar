from datetime import date, timedelta

from scripts.compute_decision_outcomes import entry_day, needs_work, outcome_values


def _s(start, closes):
    d0 = date.fromisoformat(start)
    return [((d0 + timedelta(days=i)).isoformat(), c) for i, c in enumerate(closes)]


def test_entry_is_next_day():
    assert entry_day("2026-11-15") == "2026-11-16"


def test_outcome_values_only_due_horizons():
    stock = _s("2026-01-01", [100.0] * 20 + [110.0] * 210)
    idx = _s("2026-01-01", [10.0] * 20 + [10.5] * 210)
    v = outcome_values("2026-01-02", stock, idx, today=date(2026, 3, 1))
    assert abs(v["ret_28d"] - 0.10) < 1e-9
    assert abs(v["mkt_28d"] - 0.05) < 1e-9
    assert v["ret_84d"] is None and v["mkt_84d"] is None     # 84일이 아직 안 지남


def test_needs_work():
    today = date(2026, 3, 1)
    assert needs_work("2026-02-20", None, today)                          # 시작가 없음
    full = {"entry_price": 1.0, "ret_28d": None, "ret_84d": None, "ret_182d": None}
    assert needs_work("2026-01-20", full, today)                          # 28일 지났는데 비어 있음
    assert not needs_work("2026-02-20", full, today)                      # 아직 기간 전
    assert not needs_work("2025-09-01", {**full, "ret_28d": 0.1, "ret_84d": 0.1}, today)   # 182일 아직, 나머지 채움
