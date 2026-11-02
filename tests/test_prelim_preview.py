from datetime import date

from src.analyzers.theme_earnings import (compute_prelim_preview, latest_prelims, prelim_market_median, prelim_quarter_end,
                                          prelim_rev_yoy)


def test_prelim_quarter_end():
    assert prelim_quarter_end(date(2026, 11, 2)) == "2026-09-30"
    assert prelim_quarter_end(date(2027, 1, 20)) == "2026-12-31"
    assert prelim_quarter_end(date(2026, 4, 1)) == "2026-03-31"
    assert prelim_quarter_end(date(2026, 7, 15)) == "2026-06-30"


def test_prelim_rev_yoy_only_checked_quarterly_values():
    assert prelim_rev_yoy({"revenue_yoy_pct": 12.5}) == 0.125
    assert prelim_rev_yoy({"revenue_yoy_pct": None}) is None            # 증감률이 금액과 안 맞아 수집기가 비운 값
    assert prelim_rev_yoy({"revenue_yoy_pct": 5.0, "monthly": True}) is None
    assert prelim_rev_yoy({"revenue_yoy_pct": 5.0, "annual": True}) is None


def test_latest_prelims_picks_quarter_and_latest_amendment():
    q = "2026-09-30"
    rows = [{"stock_code": "A", "rcept_no": "20261020000100", "payload": {"period_end": q, "revenue_yoy_pct": 10.0}},
            {"stock_code": "A", "rcept_no": "20261028000200", "payload": {"period_end": q, "revenue_yoy_pct": 8.0}},   # 정정
            {"stock_code": "B", "rcept_no": "20261021000300", "payload": {"period_end": "2026-06-30", "revenue_yoy_pct": 50}},
            {"stock_code": "C", "rcept_no": "20261022000400", "payload": {"period_end": q, "revenue_yoy_pct": None}}]
    assert latest_prelims(rows, q) == {"A": 0.08}


def test_preview_counts_without_ratio():
    prelims = {f"X{i}": i / 100 for i in range(25)}          # 0%~24%, 중앙값 12%
    prelims.update({"A": 0.30, "B": 0.05})
    med = prelim_market_median(prelims)
    members = [{"ticker": "A"}, {"ticker": "B"}, {"ticker": "Z"}]
    p = compute_prelim_preview(members, prelims, med, "2026-09-30")
    assert p == {"quarter": "2026-Q3", "n": 2, "beat": 1, "median": med}
    # 표본이 적으면 중앙값 없이 건수만
    assert prelim_market_median({"A": 0.1}) is None
    assert compute_prelim_preview(members, {"A": 0.1}, None, "2026-09-30")["beat"] is None
