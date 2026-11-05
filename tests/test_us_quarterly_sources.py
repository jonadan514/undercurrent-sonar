"""미국 분기 재무 출처 정리(2026-11-05) - 공시 원본 표 분기를 캐시 모양 DataFrame으로."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.quarterly_financials import quarters_to_income_df  # noqa: E402
from src.analyzers.company_growth import quarterly_margin_change, quarterly_revenue_yoy  # noqa: E402


def _q(y, q, rev, oi):
    return {"fiscal_year": y, "fiscal_quarter": q, "revenue": rev, "operating_income": oi}


def test_quarters_to_income_df_feeds_margin_and_yoy():
    qs = [_q(2026, 3, 120, 24), _q(2026, 2, 110, 20), _q(2026, 1, 100, 15), _q(2025, 4, 105, 16), _q(2025, 3, 100, 15)]
    df = quarters_to_income_df(qs)
    assert list(df.index) == ["Total Revenue", "Operating Income"] and str(df.columns[0].date()) == "2026-09-30"
    m = quarterly_margin_change(df)
    assert m["status"] == "개선" and abs(m["now"] - 0.20) < 1e-9 and abs(m["year_ago"] - 0.15) < 1e-9
    assert abs(quarterly_revenue_yoy(df)["yoy"] - 0.20) < 1e-9


def test_quarters_to_income_df_empty_and_gap():
    assert quarters_to_income_df([]) is None
    df = quarters_to_income_df([_q(2026, 3, 120, 24), _q(2025, 3, 100, None)])   # 1년 전 영업이익 없음 -> 데이터부족
    assert quarterly_margin_change(df) is None and abs(quarterly_revenue_yoy(df)["yoy"] - 0.2) < 1e-9
