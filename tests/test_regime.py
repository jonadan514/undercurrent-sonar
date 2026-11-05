"""시장 환경 축(2026-11-05)."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzers import regime as r  # noqa: E402


def _series(vals, start=date(2025, 1, 1)):
    return [((start + timedelta(days=i)).isoformat(), v) for i, v in enumerate(vals)]


def test_flat_then_jump_is_up_and_high():
    vals = [10 + (i % 5) * 0.1 for i in range(300)] + [10 + 0.05 * k for k in range(1, 21)]   # 마지막 4주 꾸준히 오름
    st = r.indicator_state(_series(vals), "2030-01-01")
    assert st["dir"] == "up" and st["level"] == "high"


def test_insufficient_data_is_none_not_judgment():
    st = r.indicator_state(_series([1.0] * 50), "2030-01-01")
    assert st["level"] is None and st["dir"] is None and st["n"] == 50


def test_flows_cumulative_sign_and_direction():
    vals = [100.0 if i % 2 else -100.0 for i in range(300)] + [-500.0] * 20   # 마지막 20일 크게 순매도
    st = r.indicator_state(_series(vals), "2030-01-01", cumulative=True)
    assert st["level"] == "low" and st["dir"] == "down"


def test_combos_risk_off_and_missing_axis():
    up = [10 + (i % 5) * 0.1 for i in range(300)] + [10 + 0.1 * k for k in range(1, 21)]
    flat = [10 + (i % 5) * 0.1 for i in range(320)]
    s = {"vix": _series(up), "hy_spread": _series(up), "dxy": _series(flat), "us10y": _series(flat)}
    st = r.market_state(s, "US", "2030-01-01")
    assert [c["id"] for c in st["combos"]] == ["risk_off"]
    st2 = r.market_state({"vix": _series(up)}, "US", "2030-01-01")   # 신용 축 데이터 없음 -> 위험 회피 판정 안 함
    assert st2["combos"] == [] and st2["axes"]["credit"]["dir"] is None


def test_dedupe_only_for_kr_rates():
    pts = [("2026-01-01", 3.0), ("2026-01-02", 3.0), ("2026-01-03", 3.1)]
    assert r._dedupe(pts) == [("2026-01-01", 3.0), ("2026-01-03", 3.1)]
