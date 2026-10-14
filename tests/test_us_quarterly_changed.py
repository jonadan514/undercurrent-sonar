"""미국 분기 재무 정기 수집 - 바뀐 분기만 저장한다.

quarterly_financials_raw는 수집일마다 행을 쌓는 이력 표라, 매주 같은 값을 다시 넣으면
주당 약 4,500행이 쌓인다. 새 분기와 값이 바뀐 분기(정정)만 남기고, 같은 값은 건너뛴다.
네트워크·DB를 타지 않는다.
"""
from __future__ import annotations

from scripts.collect_us_quarterly_financials import changed_quarters

Q = {"revenue": 100.0e6, "operating_income": 20.0e6, "net_income": 15.0e6, "fs_div": None}


def test_처음_보는_분기는_저장한다():
    assert changed_quarters({(2026, 3): Q}, {}) == {(2026, 3): Q}


def test_값이_같으면_건너뛴다():
    assert changed_quarters({(2026, 2): Q}, {(2026, 2): (100.0e6, 20.0e6, 15.0e6)}) == {}


def test_Turso가_문자열로_돌려줘도_같은_값이면_건너뛴다():
    assert changed_quarters({(2026, 2): Q}, {(2026, 2): ("100000000.0", "20000000.0", "15000000.0")}) == {}


def test_정정으로_값이_바뀌면_새로_저장한다():
    assert changed_quarters({(2026, 2): Q}, {(2026, 2): (99.0e6, 20.0e6, 15.0e6)}) == {(2026, 2): Q}


def test_비어있던_값이_채워지면_저장한다():
    """None -> 값은 '바뀜'이다(예: 영업이익이 나중에 공시됨)."""
    assert changed_quarters({(2026, 2): Q}, {(2026, 2): (100.0e6, None, 15.0e6)}) == {(2026, 2): Q}


def test_둘_다_비어있으면_같다():
    q = {**Q, "operating_income": None}
    assert changed_quarters({(2026, 2): q}, {(2026, 2): (100.0e6, None, 15.0e6)}) == {}
