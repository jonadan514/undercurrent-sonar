"""워치리스트 밸류·성장 지표 채우기 (scripts/compute_watchlist_valuation.py).

계산 자체는 test_company_valuation.py / test_company_growth.py가 이미 덮는다.
여기서 보는 건 스크립트가 운영 DB와 주고받는 부분이다:
  - Turso가 숫자를 문자열로 돌려줘도 시가총액 나눗셈이 죽지 않는가
  - PSR을 못 구한 종목을 3등분 분모에서 빼먹지 않는가(빼면 "3곳 미만" 기준이 달라진다)
  - 적자 기업의 PER을 0으로 뭉개지 않고 NULL로 두는가
  - 연차 재무제표가 없는 종목의 성장 지표가 None으로 남고 "역성장"으로 새지 않는가
  - fundamentals_cache DataFrame(NaN 섞인 열)이 company_growth로 안전하게 넘어가는가
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from compute_watchlist_valuation import ensure_columns, income_periods, load_candidates, run
from src.analyzers.company_growth import FLAT, GROWING, SHRINKING
from src.analyzers.company_valuation import CHEAP, EXPENSIVE, MID
from src.db.fundamentals_cache import ensure_schema as ensure_fundamentals_schema, upsert_statement_rows
from src.db.quarterly_financials import ensure_schema as ensure_raw_schema, insert_quarter

# 실제 워치리스트 표와 같은 이름·타입만 추려 만든다(스크리닝 스크립트가 만드는 표는
# 컬럼이 훨씬 많지만 여기서 쓰는 건 market/symbol/market_cap뿐이다).
CANDIDATES_DDL = """CREATE TABLE watchlist_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  market TEXT NOT NULL, symbol TEXT NOT NULL, name TEXT, market_cap REAL
)"""

# 최근 4분기: 2026Q3, Q2, Q1, 2025Q4
RECENT_4Q = [(2026, 3), (2026, 2), (2026, 1), (2025, 4)]


def _seed(conn, symbol, market, market_cap, revenue_per_q, net_income_per_q=10.0, quarters=RECENT_4Q):
    conn.execute(
        "INSERT INTO watchlist_candidates (market, symbol, name, market_cap) VALUES (?, ?, ?, ?)",
        (market, symbol, f"{symbol} 주식회사", market_cap),
    )
    for year, quarter in quarters:
        insert_quarter(
            conn, symbol, market, year, quarter,
            {"revenue": revenue_per_q, "operating_income": 5.0,
             "net_income": net_income_per_q, "fs_div": "CFS"},
            source="test", currency="KRW", collected_at="2026-10-01T00:00:00",
        )


def _seed_annual_income(conn, symbol, market, yearly: dict[str, dict]):
    """yearly: {'2026-12-31': {'Total Revenue': ..., 'Operating Income': ...}, ...}
    fundamentals_cache가 실제로 받는 모양(get_cached_financials_bulk 경유)과 같은
    형태로 연차 손익계산서를 넣는다 - upsert_statement_rows()가 기대하는 DataFrame
    (컬럼=회계기간, 인덱스=계정명)을 그대로 조립한다."""
    df = pd.DataFrame({pd.Timestamp(period): pd.Series(accounts) for period, accounts in yearly.items()})
    upsert_statement_rows(conn, symbol, market, "income", df, fetched_at="2026-09-30T00:00:00")


def _4y_income(revenues, op_incomes=(None, None, None, None)):
    """최신순 4개 연도(2026, 2025, 2024, 2023) -> _seed_annual_income()용 dict."""
    years = ("2026-12-31", "2025-12-31", "2024-12-31", "2023-12-31")
    out = {}
    for year, rev, oi in zip(years, revenues, op_incomes):
        accounts = {"Total Revenue": rev}
        if oi is not None:
            accounts["Operating Income"] = oi
        out[year] = accounts
    return out


def _read(conn, market="KR"):
    rows = conn.execute(
        "SELECT symbol, psr, per, valuation_tier, revenue_cagr_3y, revenue_yoy, "
        "op_margin_direction, growth_tier FROM watchlist_candidates WHERE market = ?",
        (market,),
    ).fetchall()
    return {r[0]: tuple(r[1:]) for r in rows}


@pytest.fixture
def db(turso_like_db):
    turso_like_db.execute(CANDIDATES_DDL)
    ensure_raw_schema(turso_like_db)
    ensure_fundamentals_schema(turso_like_db)
    ensure_columns(turso_like_db)
    return turso_like_db


def test_psr_per_written_and_tiered(db):
    # 매출 합은 각각 400 / 800 / 1600, 시가총액은 전부 4000 -> PSR 10 / 5 / 2.5
    _seed(db, "AAA", "KR", 4000.0, revenue_per_q=100.0)
    _seed(db, "BBB", "KR", 4000.0, revenue_per_q=200.0)
    _seed(db, "CCC", "KR", 4000.0, revenue_per_q=400.0)

    run(db, ["KR"])
    got = _read(db)

    assert got["CCC"][0] == pytest.approx(2.5)
    assert got["BBB"][0] == pytest.approx(5.0)
    assert got["AAA"][0] == pytest.approx(10.0)
    # 순이익 합 40, 시총 4000 -> PER 100
    assert got["AAA"][1] == pytest.approx(100.0)
    # 3종목이면 정확히 한 칸씩
    assert (got["CCC"][2], got["BBB"][2], got["AAA"][2]) == (CHEAP, MID, EXPENSIVE)


def test_market_cap_as_string_does_not_crash(db):
    """Turso는 숫자를 문자열로 돌려준다 - load_candidates()가 float으로 되돌려야 한다."""
    _seed(db, "AAA", "KR", 4000, revenue_per_q=100.0)   # INTEGER로 들어가 문자열로 돌아온다

    loaded = load_candidates(db, "KR")
    assert loaded == [{"symbol": "AAA", "market_cap": 4000.0}]

    run(db, ["KR"])
    assert _read(db)["AAA"][0] == pytest.approx(10.0)


def test_missing_quarters_leave_null_but_still_count_in_denominator(db):
    """분기가 비는 종목도 3등분 분모에 남는다 (원칙 4 - 데이터부족은 탈락이 아니다).

    PSR을 구한 종목이 2곳뿐이면 '3곳 미만'이라 **전체**가 등급 없음이어야 한다.
    데이터부족 종목을 분모에서 빼면 2곳만으로 싼/비싼을 나눠 버린다.
    """
    _seed(db, "AAA", "KR", 4000.0, revenue_per_q=100.0)
    _seed(db, "BBB", "KR", 4000.0, revenue_per_q=200.0)
    _seed(db, "GAP", "KR", 4000.0, revenue_per_q=100.0,
          quarters=[(2026, 3), (2026, 2), (2025, 4), (2025, 3)])   # 2026Q1이 빔
    _seed(db, "NONE", "KR", None, revenue_per_q=100.0)             # 시가총액 없음

    run(db, ["KR"])
    got = _read(db)

    assert got["GAP"][0] is None and got["NONE"][0] is None
    assert all(v[2] is None for v in got.values())


def test_loss_making_company_gets_null_per_not_zero(db):
    """적자면 PER은 NULL. 0으로 넣으면 화면에서 'PER 0배'라는 거짓말이 된다."""
    _seed(db, "AAA", "KR", 4000.0, revenue_per_q=100.0, net_income_per_q=-10.0)
    _seed(db, "BBB", "KR", 4000.0, revenue_per_q=200.0, net_income_per_q=10.0)
    _seed(db, "CCC", "KR", 4000.0, revenue_per_q=400.0, net_income_per_q=10.0)

    run(db, ["KR"])
    got = _read(db)

    assert got["AAA"][1] is None
    assert got["AAA"][0] is not None   # 적자여도 PSR과 등급은 그대로 나온다
    assert got["AAA"][2] == EXPENSIVE


def test_other_market_untouched(db):
    """--market KR로 돌려도 US 행은 건드리지 않는다."""
    _seed(db, "AAA", "KR", 4000.0, revenue_per_q=100.0)
    _seed(db, "MSFT", "US", 4000.0, revenue_per_q=100.0)

    run(db, ["KR"])

    assert _read(db, "US")["MSFT"] == (None, None, None, None, None, None, None)


# ── income_periods() - fundamentals_cache DataFrame 변환 ────────────────────

def test_income_periods_converts_dataframe_to_period_tuples():
    df = pd.DataFrame({
        pd.Timestamp("2026-12-31"): pd.Series({"Total Revenue": 133.1}),
        pd.Timestamp("2025-12-31"): pd.Series({"Total Revenue": 121.0}),
    })
    periods = income_periods(df)
    assert periods == [
        ("2026-12-31", {"Total Revenue": 133.1}),
        ("2025-12-31", {"Total Revenue": 121.0}),
    ]


def test_income_periods_drops_nan_from_misaligned_columns():
    """한 시점에만 있는 계정은 다른 열에서 NaN으로 채워진다 - None으로 착각되면
    안 되니 dropna()로 미리 걸러야 한다(company_growth._pick은 NaN을 값으로 오인한다)."""
    df = pd.DataFrame({
        pd.Timestamp("2026-12-31"): pd.Series({"Total Revenue": 100.0, "Extra Item": 5.0}),
        pd.Timestamp("2025-12-31"): pd.Series({"Total Revenue": 90.0}),   # Extra Item 없음 -> NaN
    })
    periods = income_periods(df)
    period_2025 = dict(periods)["2025-12-31"]
    assert "Extra Item" not in period_2025


def test_income_periods_empty_dataframe_returns_empty_list():
    assert income_periods(pd.DataFrame()) == []
    assert income_periods(None) == []


# ── 성장 지표 - run()을 통한 배관 검증 ───────────────────────────────────────

def test_growth_computed_and_written(db):
    _seed(db, "AAA", "KR", 4000.0, revenue_per_q=100.0)
    _seed_annual_income(db, "AAA", "KR", _4y_income(revenues=(133.1, 121.0, 110.0, 100.0)))

    run(db, ["KR"])
    got = _read(db)

    cagr, yoy = got["AAA"][3], got["AAA"][4]
    assert cagr == pytest.approx(0.10, abs=1e-6)
    assert yoy == pytest.approx(133.1 / 121.0 - 1)
    assert got["AAA"][6] == GROWING   # growth_tier


def test_no_annual_income_leaves_growth_columns_null_not_shrinking(db):
    """원칙 4 - 연차 재무제표가 아예 없는 종목은 데이터부족(None)이지 '역성장'이 아니다."""
    _seed(db, "AAA", "KR", 4000.0, revenue_per_q=100.0)   # 분기 재무만 있고 연차 없음

    run(db, ["KR"])
    got = _read(db)

    assert got["AAA"][3] is None   # revenue_cagr_3y
    assert got["AAA"][4] is None   # revenue_yoy
    assert got["AAA"][6] is None   # growth_tier - SHRINKING이 아니다


def test_shrinking_company_gets_shrinking_tier(db):
    _seed(db, "AAA", "KR", 4000.0, revenue_per_q=100.0)
    _seed_annual_income(db, "AAA", "KR", _4y_income(revenues=(80.0, 90.0, 95.0, 100.0)))

    run(db, ["KR"])
    got = _read(db)

    assert got["AAA"][3] < 0
    assert got["AAA"][6] == SHRINKING


def test_op_margin_direction_written(db):
    _seed(db, "AAA", "KR", 4000.0, revenue_per_q=100.0)
    _seed_annual_income(db, "AAA", "KR", _4y_income(
        revenues=(1000.0, 900.0, 950.0, 1000.0),
        op_incomes=(100.0, 90.0, 70.0, 50.0),   # 최신 10% > 3년전 5% -> 개선
    ))

    run(db, ["KR"])
    got = _read(db)

    assert got["AAA"][5] == "개선"   # op_margin_direction


def test_growth_and_valuation_computed_independently(db):
    """밸류(3등분)와 성장(절대 기준)이 서로의 계산을 방해하지 않는다 - 후보가
    하나뿐이라 밸류 3등분은 데이터부족(3곳 미만)이어도 성장은 정상 계산돼야 한다."""
    _seed(db, "AAA", "KR", 4000.0, revenue_per_q=100.0)
    _seed_annual_income(db, "AAA", "KR", _4y_income(revenues=(133.1, 121.0, 110.0, 100.0)))

    run(db, ["KR"])
    got = _read(db)

    assert got["AAA"][2] is None       # valuation_tier - 후보 1곳뿐이라 데이터부족
    assert got["AAA"][6] == GROWING    # growth_tier - 절대 기준이라 후보 수와 무관


# ── FCF 수익률 - run()을 통한 배관 검증 (2026-10-19) ─────────────────────────

def _seed_annual_cashflow(conn, symbol, market, yearly: dict[str, dict]):
    df = pd.DataFrame({pd.Timestamp(period): pd.Series(accounts) for period, accounts in yearly.items()})
    upsert_statement_rows(conn, symbol, market, "cashflow", df, fetched_at="2026-09-30T00:00:00")


def _read_fcf(conn, market="KR"):
    rows = conn.execute(
        "SELECT symbol, fcf_yield_3y, fcf_yield_latest, fcf_negative_years, fcf_latest_year "
        "FROM watchlist_candidates WHERE market = ?", (market,)).fetchall()
    return {r[0]: tuple(r[1:]) for r in rows}


def test_fcf_yield_computed_and_written(db):
    _seed(db, "AAA", "KR", 1000.0, revenue_per_q=100.0)
    _seed_annual_cashflow(db, "AAA", "KR", {
        "2025-12-31": {"Free Cash Flow": 200.0},
        "2024-12-31": {"Free Cash Flow": -50.0},
        "2023-12-31": {"Free Cash Flow": 150.0},
    })
    run(db, ["KR"])
    y3, latest, neg, year = _read_fcf(db)["AAA"]
    assert float(y3) == pytest.approx(0.10)
    assert float(latest) == pytest.approx(0.20)
    assert int(neg) == 1
    assert year == "2025"


def test_no_cashflow_leaves_fcf_null(db):
    """원칙 4 - 현금흐름표가 없으면 0이 아니라 NULL(데이터부족)."""
    _seed(db, "AAA", "KR", 1000.0, revenue_per_q=100.0)
    run(db, ["KR"])
    assert _read_fcf(db)["AAA"] == (None, None, None, None)
