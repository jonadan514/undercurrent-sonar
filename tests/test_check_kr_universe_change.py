"""한국 유니버스 갱신 비교·안전장치 (scripts/check_kr_universe_change.py)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_kr_universe_change", Path(__file__).resolve().parent.parent / "scripts" / "check_kr_universe_change.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def _u(n, start=0):
    return [{"symbol": f"{i:06d}", "name": f"종목{i}", "market_cap": 1e12 - i} for i in range(start, start + n)]


def test_small_weekly_churn_passes_and_sorted_by_cap():
    old, new = _u(687), _u(687, start=10)
    added, removed = m.compare(old, new)
    assert len(added) == 10 and len(removed) == 10
    assert added[0]["symbol"] == "000687"            # 시총 큰 순
    assert m.check(old, new, added, removed) is None


def test_broken_fetch_is_blocked():
    old = _u(687)
    assert "비어" in m.check(old, [], [], old)
    half = _u(300)
    a, r = m.compare(old, half)
    assert "15%" in m.check(old, half, a, r)
    swap = _u(687, start=1000)
    a, r = m.compare(old, swap)
    assert m.check(old, swap, a, r) is not None
