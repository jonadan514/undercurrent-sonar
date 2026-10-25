"""테마 동료 비교용 FCF 수익률(2026-10-25) - 시가총액 출처, 금융업 제외, 데이터부족."""
import sys
from pathlib import Path

import pandas as pd

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
