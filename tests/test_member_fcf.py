"""테마 동료 비교용 FCF 수익률(2026-10-25) - 시가총액 출처, 금융업 제외, 데이터부족."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from compute_theme_earnings import member_fcf  # noqa: E402


def _cf(values):
    cols = [pd.Timestamp(f"{y}-12-31") for y in (2025, 2024, 2023)]
    return pd.DataFrame({c: {"Free Cash Flow": v} for c, v in zip(cols, values)})


def test_uses_info_market_cap_when_no_universe_cap():
    r = member_fcf({"info": {"marketCap": 1000, "sector": "Technology"}, "cashflow": _cf([30, 20, 10])}, None)
    assert abs(r["yield_3y"] - 0.02) < 1e-9 and r["negative_years"] == 0


def test_universe_cap_wins():
    r = member_fcf({"info": {"marketCap": 1000}, "cashflow": _cf([30, 20, 10])}, 2000)
    assert abs(r["yield_3y"] - 0.01) < 1e-9


def test_financials_skipped():
    r = member_fcf({"info": {"marketCap": 1000, "sector": "Financial Services"}, "cashflow": _cf([30, 20, 10])}, None)
    assert r == {"yield_3y": None, "negative_years": None}


def test_missing_data_is_none():
    assert member_fcf(None, 1000) == {"yield_3y": None, "negative_years": None}
    assert member_fcf({"info": {}, "cashflow": _cf([30, 20, 10])}, None)["yield_3y"] is None   # 시가총액 없음


def test_universe_peer_rows_skips_all_missing():
    """업종 동료 비교용 유니버스 값(2026-11-11) - 세 값이 다 없으면 줄을 만들지 않고, 하나라도 있으면 나머지는 None으로."""
    import pandas as pd
    from compute_theme_earnings import universe_peer_rows
    rev = pd.Series([120.0, 110, 105, 100, 100.0])   # 최신이 앞 - 1년 전 대비 +20%
    rows = universe_peer_rows({"US": ["AAA", "BBB", "CCC"]}, "2026-11-09", "t", {"AAA": rev},
                              {"BBB": {"now": 0.25}}, lambda t: None)
    assert [(r[1], r[3], r[4], r[5]) for r in rows] == [("AAA", pytest.approx(0.2), None, None), ("BBB", None, 0.25, None)]
