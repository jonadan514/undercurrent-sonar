"""미국 유니버스 목록 갱신의 비교·안전장치 (scripts/refresh_us_index_lists.py)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "refresh_us_index_lists", Path(__file__).resolve().parent.parent / "scripts" / "refresh_us_index_lists.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def test_diff_and_normal_change_passes():
    old = [f"T{i}" for i in range(500)] + ["EA"]
    new = [f"T{i}" for i in range(500)] + ["NEW"]
    added, removed = m.diff_lists(old, new)
    assert added == ["NEW"] and removed == ["EA"]
    assert m.check("sp500", new, added, removed) is None


def test_guards_block_broken_or_vandalized_lists():
    assert "정상 범위" in m.check("sp500", ["A"] * 0 + [f"T{i}" for i in range(100)], [], [])
    assert "중복" in m.check("sp400", [f"T{i}" for i in range(399)] + ["T1"], [], [])
    big = [f"N{i}" for i in range(20)]
    assert "허용" in m.check("sp500", [f"T{i}" for i in range(500)], big, big)
