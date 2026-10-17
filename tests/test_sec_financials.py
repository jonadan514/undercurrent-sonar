"""SEC companyfacts -> 분기 값 (src/collectors/sec_financials.py)."""
from src.collectors.sec_financials import quarterly_values


def _f(start, end, val, filed="2026-01-01"):
    return {"start": start, "end": end, "val": val, "filed": filed}


def _facts(**concepts):
    return {"facts": {"us-gaap": {c: {"units": {"USD": items}} for c, items in concepts.items()}}}


CAL_2025 = [_f("2025-01-01", "2025-03-31", 100), _f("2025-04-01", "2025-06-30", 110),
            _f("2025-07-01", "2025-09-30", 120), _f("2025-01-01", "2025-12-31", 470),   # 4분기 = 470 - 330 = 140
            _f("2025-01-01", "2025-06-30", 210)]                                         # 반기 누적은 무시


def test_q4_derived_from_annual_and_ytd_ignored():
    v = quarterly_values(_facts(Revenues=CAL_2025))
    assert v[(2025, 4)]["revenue"] == 140 and v[(2025, 4)]["derived"] == "annual_minus_9m"
    assert v[(2025, 2)]["revenue"] == 110 and v[(2025, 2)]["derived"] == "reported"
    assert len(v) == 4


def test_latest_filed_wins_and_concept_with_more_quarters_chosen():
    items = CAL_2025 + [_f("2025-04-01", "2025-06-30", 111, filed="2026-03-01")]   # 정정
    old = [_f("2025-01-01", "2025-03-31", 999)]                                        # 분기 1개뿐인 계정
    v = quarterly_values(_facts(Revenues=old, RevenueFromContractWithCustomerExcludingAssessedTax=items))
    assert v[(2025, 2)]["revenue"] == 111 and v[(2025, 1)]["revenue"] == 100


def test_no_q4_without_three_quarters_and_old_quarters_dropped():
    items = [_f("2025-01-01", "2025-03-31", 100), _f("2025-01-01", "2025-12-31", 470),
             _f("2022-01-01", "2022-03-31", 50)]
    v = quarterly_values(_facts(Revenues=items))
    assert (2025, 4) not in v and (2022, 1) not in v and (2025, 1) in v


def test_non_calendar_fiscal_quarters_and_other_lines():
    # 마이크론식 5월 말 분기
    items = [_f("2025-03-01", "2025-05-31", 9301), _f("2025-06-01", "2025-08-31", 11315)]
    op = [_f("2025-03-01", "2025-05-31", 2169)]
    v = quarterly_values(_facts(Revenues=items, OperatingIncomeLoss=op))
    assert v[(2025, 2)]["revenue"] == 9301 and v[(2025, 2)]["operating_income"] == 2169
    assert v[(2025, 3)]["operating_income"] is None


def test_bank_revenue_is_net_interest_plus_noninterest_income():
    nii = [_f("2025-01-01", "2025-03-31", 600), _f("2025-04-01", "2025-06-30", 650)]
    nonint = [_f("2025-01-01", "2025-03-31", 100), _f("2025-04-01", "2025-06-30", 110)]
    ni = [_f("2025-04-01", "2025-06-30", 300)]
    v = quarterly_values(_facts(InterestIncomeExpenseNet=nii, NoninterestIncome=nonint, NetIncomeLoss=ni))
    assert v[(2025, 2)]["revenue"] == 760 and v[(2025, 2)]["net_income"] == 300
    assert v[(2025, 2)]["derived"] == "bank_nii_plus_noninterest"
    # 일반 매출 계정이 있으면 은행식 합산은 쓰지 않는다
    v2 = quarterly_values(_facts(Revenues=CAL_2025, InterestIncomeExpenseNet=nii, NoninterestIncome=nonint))
    assert v2[(2025, 2)]["revenue"] == 110
