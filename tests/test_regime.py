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


def test_describe_and_compact_have_no_numbers():
    import re
    up = [10 + (i % 5) * 0.1 for i in range(300)] + [10 + 0.1 * k for k in range(1, 21)]
    flat = [10 + (i % 5) * 0.1 for i in range(320)]
    st = r.market_state({"vix": _series(up), "hy_spread": _series(up), "dxy": _series(flat), "us10y": _series(flat)}, "US", "2030-01-01")
    d = r.describe(st)
    assert d["미국 시장 환경(최근 4주, 정해진 조합)"].startswith("위험 회피")
    assert not any(re.search(r"\d+(\.\d+)?\s*(%|%p|bp|포인트|원|달러)|\d\.\d", v) for v in d.values())   # 값·변화 숫자 없음
    c = r.compact(st)
    assert c["axes"]["vol"]["dir"] == "up" and "rules" not in c


def test_last_friday():
    import sys as _s
    from pathlib import Path as _P
    _s.path.insert(0, str(_P(__file__).resolve().parent.parent / "scripts"))
    from compute_market_regime import last_friday
    assert last_friday(date(2026, 11, 8)).isoformat() == "2026-11-06"    # 일요일
    assert last_friday(date(2026, 11, 6)).isoformat() == "2026-10-30"    # 금요일 당일은 그 전 금요일
