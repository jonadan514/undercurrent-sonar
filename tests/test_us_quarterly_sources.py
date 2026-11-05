"""미국 분기 재무 출처 정리(2026-11-05) - 공시 원본 표 분기를 캐시 모양 DataFrame으로."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.quarterly_financials import quarters_to_income_df  # noqa: E402
from src.analyzers.company_growth import pick_latest, quarterly_margin_change, quarterly_revenue_yoy  # noqa: E402


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


def test_pick_latest_prefers_newer_then_raw():
    raw, cache = {"quarter": "2026-Q3", "src": "raw"}, {"quarter": "2026-Q3", "src": "cache"}
    assert pick_latest(raw, cache)["src"] == "raw"                                   # 같은 분기 -> 공시 원본
    assert pick_latest({"quarter": "2026-Q2", "src": "raw"}, cache)["src"] == "cache"  # 캐시가 더 최근
    assert pick_latest({"quarter": "2026-Q4", "src": "raw"}, cache)["src"] == "raw"
    assert pick_latest(None, cache)["src"] == "cache" and pick_latest(raw, None)["src"] == "raw"
    assert pick_latest(None, None) is None


# ── 52/53주 회계연도 분기 이름·거둬들인 분기 (2026-11-05, 코카콜라 2026 분기 중복) ─────────────────
from datetime import date  # noqa: E402

from src.db.quarterly_financials import _best_per_quarter, calendar_quarter, withdrawn_keys  # noqa: E402


def test_calendar_quarter_grace_for_52_53_week_years():
    assert calendar_quarter(date(2026, 4, 3)) == (2026, 1)    # KO 2026 1분기
    assert calendar_quarter(date(2026, 10, 2)) == (2026, 3)
    assert calendar_quarter(date(2027, 1, 1)) == (2026, 4)
    assert calendar_quarter(date(2026, 9, 26)) == (2026, 3)
    assert calendar_quarter(date(2026, 1, 31)) == (2026, 1)   # 1월 말 결산(소매)은 그대로
    assert calendar_quarter(date(2026, 10, 31)) == (2026, 4)  # 10월 말 결산도 그대로


def test_withdrawn_keys_only_newer_and_alive():
    prev = {(2026, 4): (13.4, 4.5, 4.0), (2026, 3): (13.4, 4.7, 4.4), (2025, 4): (1, 1, 1), (2027, 1): (None, None, None)}
    assert withdrawn_keys({(2026, 3): {}, (2026, 2): {}}, prev) == [(2026, 4)]   # 이미 거둔 (2027,1)은 다시 안 넣음
    assert withdrawn_keys({}, prev) == []


def _rec(y, q, rev, src="SEC", at="2026-11-01", derived="reported"):
    return {"fiscal_year": y, "fiscal_quarter": q, "revenue": rev, "operating_income": None if rev is None else 1.0,
            "net_income": None, "source": src, "fs_div": "NA", "collected_at": at, "derived": derived}


def test_best_per_quarter_skips_withdrawn_and_unfinished():
    recs = [_rec(2026, 3, 13.4, at="2026-10-30"), _rec(2026, 3, None, at="2026-11-05", derived="withdrawn"),   # SEC가 거둬들임
            _rec(2026, 3, 13.3, src="yfinance"),                                         # 다른 출처는 살아 있음
            _rec(2026, 2, 12.5), _rec(2026, 4, 9.9)]                                      # 2026-Q4는 아직 안 끝남
    best = _best_per_quarter(recs, today=date(2026, 11, 5))
    assert sorted(best) == [(2026, 2), (2026, 3)]
    assert best[(2026, 3)]["source"] == "yfinance"
    assert (2026, 4) in _best_per_quarter(recs, today=date(2027, 1, 2))
    assert (2026, 1) in _best_per_quarter([_rec(2026, 1, None)], today=date(2026, 11, 5))   # 금액만 빈 분기는 그대로(원칙 4)
