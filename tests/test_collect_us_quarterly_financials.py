"""미국 분기 재무 추출 (docs/REDESIGN_SPEC.md 4-1, scripts/collect_us_quarterly_financials.py).

yfinance quarterly_financials DataFrame(행=계정과목, 열=분기 말일)을 quarterly_financials_raw
형식으로 바꾸는 순수 함수만 테스트한다. yfinance 호출(fetch_quarterly)은 네트워크가
필요해 테스트하지 않는다(작업지시서 22장).
"""
from __future__ import annotations

import math

import pandas as pd

from scripts.collect_us_quarterly_financials import extract_quarters, quarter_of


def _df(**cols: dict) -> pd.DataFrame:
    """{'2026-06-30': {'Total Revenue': 1000, ...}, ...} -> yfinance 모양 DataFrame."""
    return pd.DataFrame({pd.Timestamp(k): v for k, v in cols.items()})


# ── 분기 판정 ─────────────────────────────────────────────────

def test_분기_말일에서_연도와_분기를_뽑는다():
    assert quarter_of(pd.Timestamp("2026-06-30")) == (2026, 2)
    assert quarter_of(pd.Timestamp("2025-12-31")) == (2025, 4)
    assert quarter_of(pd.Timestamp("2026-01-01")) == (2025, 4)   # 52/53주 회계연도 - 다음 분기 첫 14일은 앞 분기(2026-11-05)
    assert quarter_of(pd.Timestamp("2026-01-31")) == (2026, 1)


# ── 값 추출 ───────────────────────────────────────────────────

def test_매출_영업이익_순이익을_뽑는다():
    df = _df(**{"2026-06-30": {"Total Revenue": 1000, "Operating Income": 100, "Net Income": 80}})
    got = extract_quarters(df)
    assert got == {(2026, 2): {"revenue": 1000.0, "operating_income": 100.0,
                               "net_income": 80.0, "fs_div": None}}


def test_영업이익이_없으면_EBIT으로_대신한다():
    df = _df(**{"2026-06-30": {"Total Revenue": 1000, "EBIT": 90, "Net Income": 80}})
    got = extract_quarters(df)
    assert got[(2026, 2)]["operating_income"] == 90.0


def test_영업이익과_EBIT이_둘_다_있으면_영업이익을_쓴다():
    df = _df(**{"2026-06-30": {"Total Revenue": 1000, "Operating Income": 100, "EBIT": 90}})
    got = extract_quarters(df)
    assert got[(2026, 2)]["operating_income"] == 100.0


def test_행_자체가_없으면_None이다():
    """계산 불가를 탈락으로 처리하지 않는다(원칙 4) - None이 그대로 나와야 한다."""
    df = _df(**{"2026-06-30": {"Total Revenue": 1000}})
    got = extract_quarters(df)
    assert got[(2026, 2)]["operating_income"] is None
    assert got[(2026, 2)]["net_income"] is None


def test_NaN도_None으로_들어간다():
    df = _df(**{"2026-06-30": {"Total Revenue": 1000, "Net Income": math.nan}})
    got = extract_quarters(df)
    assert got[(2026, 2)]["net_income"] is None


def test_세_값이_다_없는_분기는_뺀다():
    df = _df(**{"2026-06-30": {"Total Revenue": math.nan, "Net Income": math.nan}})
    got = extract_quarters(df)
    assert got == {}


def test_fs_div는_항상_None이다():
    """연결·별도 구분이 없다 - insert_quarter()가 이걸 'NA'로 저장한다."""
    df = _df(**{"2026-06-30": {"Total Revenue": 1000}})
    got = extract_quarters(df)
    assert got[(2026, 2)]["fs_div"] is None


def test_여러_분기를_다_뽑는다():
    df = _df(**{
        "2026-06-30": {"Total Revenue": 1000},
        "2026-03-31": {"Total Revenue": 900},
        "2025-12-31": {"Total Revenue": 850},
    })
    got = extract_quarters(df)
    assert set(got.keys()) == {(2026, 2), (2026, 1), (2025, 4)}
    assert got[(2026, 2)]["revenue"] == 1000.0
    assert got[(2025, 4)]["revenue"] == 850.0


def test_한_분기만_있는_종목도_뽑힌다():
    """신규 상장 등으로 분기가 하나뿐이어도(5분기 미만) 있는 만큼은 저장한다."""
    df = _df(**{"2026-06-30": {"Total Revenue": 500}})
    got = extract_quarters(df)
    assert len(got) == 1
