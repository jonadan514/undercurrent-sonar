"""FCF 수익률 (src/analyzers/company_cashflow.py).

지키는 것:
  - 3년 평균이 대표값이고, 연속 3개 회계연도가 아니면 None(데이터부족 - 원칙 4).
  - 음수 해가 섞였는지 따로 센다 - 평균만 보면 설비투자 한 해의 출렁임이 숨는다.
  - FCF 항목이 없으면 영업현금흐름 + 자본지출로 만들되, 하나라도 없으면 그 해는 없음.
  - 시가총액이 없으면 아무것도 계산하지 않는다.
네트워크·DB를 타지 않는다.
"""
from __future__ import annotations

import pytest

from src.analyzers.company_cashflow import annual_fcf, fcf_yield


def _p(year: int, fcf=None, **kw) -> tuple[str, dict]:
    data = dict(kw)
    if fcf is not None:
        data["Free Cash Flow"] = fcf
    return (f"{year}-12-31", data)


def test_3년_평균과_최근_연도():
    periods = [_p(2025, 120.0), _p(2024, 90.0), _p(2023, 90.0)]
    r = fcf_yield(periods, 1000.0)
    assert r["yield_3y"] == pytest.approx(0.10)
    assert r["yield_latest"] == pytest.approx(0.12)
    assert r["negative_years"] == 0
    assert r["latest_year"] == "2025"


def test_정렬_순서와_무관하다():
    periods = [_p(2023, 90.0), _p(2025, 120.0), _p(2024, 90.0)]
    assert fcf_yield(periods, 1000.0)["yield_latest"] == pytest.approx(0.12)


def test_설비투자_한_해의_음수를_센다():
    periods = [_p(2025, 200.0), _p(2024, -50.0), _p(2023, 150.0)]
    r = fcf_yield(periods, 1000.0)
    assert r["yield_3y"] == pytest.approx(0.10)
    assert r["negative_years"] == 1


def test_연도가_비면_3년_평균은_데이터부족():
    """2024가 빠진 3개 기간은 '3년 평균'이 아니다 - 최근 연도 값만 낸다."""
    periods = [_p(2025, 120.0), _p(2023, 90.0), _p(2022, 90.0)]
    r = fcf_yield(periods, 1000.0)
    assert r["yield_3y"] is None
    assert r["negative_years"] is None
    assert r["yield_latest"] == pytest.approx(0.12)


def test_2개_연도뿐이면_3년_평균은_데이터부족():
    r = fcf_yield([_p(2025, 120.0), _p(2024, 90.0)], 1000.0)
    assert r["yield_3y"] is None and r["yield_latest"] == pytest.approx(0.12)


def test_시가총액이_없으면_전부_None():
    for cap in (None, 0, -5.0):
        r = fcf_yield([_p(2025, 1.0), _p(2024, 1.0), _p(2023, 1.0)], cap)
        assert r == {"yield_3y": None, "yield_latest": None, "negative_years": None, "latest_year": None}


def test_FCF_항목이_없으면_영업현금흐름에서_자본지출을_뺀다():
    assert annual_fcf({"Operating Cash Flow": 100.0, "Capital Expenditure": -30.0}) == pytest.approx(70.0)
    # 자본지출이 양수로 들어와도 빼는 방향이다
    assert annual_fcf({"Operating Cash Flow": 100.0, "Capital Expenditure": 30.0}) == pytest.approx(70.0)


def test_둘_중_하나라도_없으면_그_해는_없음():
    assert annual_fcf({"Operating Cash Flow": 100.0}) is None
    assert annual_fcf({}) is None


def test_FCF가_전혀_없으면_전부_None():
    r = fcf_yield([("2025-12-31", {}), ("2024-12-31", {})], 1000.0)
    assert r["yield_latest"] is None and r["yield_3y"] is None
