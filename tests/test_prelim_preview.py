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


def _q(y, q, rev, src="DART"):
    return {"fiscal_year": y, "fiscal_quarter": q, "revenue": rev, "source": src}


def test_dart_revenue_series_stops_at_gap():
    from src.analyzers.theme_earnings import dart_revenue_series, yoy_growth
    qs = [_q(2026, 3, 130), _q(2026, 2, 120), _q(2026, 1, 110), _q(2025, 4, 105), _q(2025, 3, 100), _q(2025, 1, 90)]
    s = dart_revenue_series(qs)
    assert len(s) == 5 and str(s.index[0].date()) == "2026-09-30"   # 2025Q2가 빠져 거기서 멈춤
    assert abs(yoy_growth(s) - 0.30) < 1e-9
    assert dart_revenue_series([_q(2026, 3, None)]) is None


def test_pick_revenue_newer_quarter_then_dart():
    import pandas as pd
    from src.analyzers.theme_earnings import dart_revenue_series, pick_revenue
    dart = dart_revenue_series([_q(2026, 3, 130), _q(2026, 2, 120), _q(2026, 1, 110), _q(2025, 4, 105), _q(2025, 3, 100)])
    yf_old = pd.Series([1, 1, 1, 1, 1], index=pd.to_datetime(["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30"]))
    assert pick_revenue(yf_old, dart)[1] == "DART"                       # DART가 3분기까지 - 더 최신
    yf_same = pd.Series([2, 2, 2, 2, 2], index=pd.to_datetime(["2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"]))
    assert pick_revenue(yf_same, dart)[1] == "DART"                      # 같은 분기면 공시 원본
    short = dart_revenue_series([_q(2026, 3, 130), _q(2026, 2, 120)])
    assert pick_revenue(yf_old, short)[1] == "yfinance"                  # DART 분기 수 부족 → yfinance
    assert pick_revenue(None, None) == (None, None)


def test_incremental_plan():
    from scripts.collect_kr_quarterly_financials import incremental_plan, target_quarter
    assert target_quarter(date(2026, 11, 2)) == (2026, 3) and target_quarter(date(2027, 2, 1)) == (2026, 4)
    full_hist = [_q(2026, 2, 1), _q(2026, 1, 1), _q(2025, 4, 1), _q(2025, 3, 1)]
    assert incremental_plan(full_hist + [_q(2026, 3, 1)], (2026, 3)) == "skip"
    assert incremental_plan(full_hist, (2026, 3)) == "one_year"
    assert incremental_plan(full_hist[:2], (2026, 3)) == "full"
    assert incremental_plan([_q(2026, 3, 1, "yfinance")] + full_hist, (2026, 3)) == "one_year"   # yfinance 행은 DART로 안 침
    assert incremental_plan([_q(2026, 3, 1), _q(2026, 2, 1), _q(2026, 1, 1), _q(2025, 4, 1)], (2026, 4)) == "full"
