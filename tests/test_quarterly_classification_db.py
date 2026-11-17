"""테마 4칸 분류 이력 저장 (docs/REDESIGN_SPEC.md 7장, src/db/quarterly_classification.py).

핵심: 같은 분기는 다시 계산하면 갱신되고, 다른 분기 행은 건드리지 않는다(이력이 쌓인다).
데이터부족(None)은 sqlite에 NULL로 저장되고 0과 구분되어 그대로 돌아와야 한다.
"""
from __future__ import annotations

import pytest

from src.db.quarterly_classification import (ensure_schema, get_classification,
                                              get_market_reference, get_theme_history,
                                              previous_classification, upsert_classification,
                                              upsert_market_reference)

FIN_ON = {"on": True, "changed": 3, "judged": 7, "ratio": 3 / 7}
FIN_OFF = {"on": False, "changed": 1, "judged": 7, "ratio": 1 / 7}
FIN_NA = {"on": None, "changed": 0, "judged": 1, "ratio": None}
NEWS_HIGH = {"high": True, "ratio": 2.1, "this_quarter": 300}
NEWS_LOW = {"high": False, "ratio": 0.8, "this_quarter": 90}
NEWS_NA = {"high": None, "ratio": None, "this_quarter": 40}


def _put(conn, theme_id="battery", market="KR", year=2026, quarter=3,
         financial=FIN_ON, news=NEWS_LOW, classification="조용한 변화", at="2026-10-01T00:00:00"):
    upsert_classification(conn, theme_id, market, year, quarter,
                          financial=financial, news=news, classification=classification,
                          computed_at=at)


def test_넣은_값을_그대로_읽는다(memory_db):
    ensure_schema(memory_db)
    _put(memory_db)
    got = get_classification(memory_db, "battery", "KR", 2026, 3)
    assert got["financial_on"] is True and got["news_high"] is False
    assert got["classification"] == "조용한 변화"
    assert got["financial_changed"] == 3 and got["financial_judged"] == 7


def test_계산한_적_없으면_None이다(memory_db):
    ensure_schema(memory_db)
    assert get_classification(memory_db, "battery", "KR", 2026, 3) is None


def test_데이터부족은_0이_아니라_None으로_돌아온다(memory_db):
    """financial_on=False(0)와 financial_on=None(데이터부족)이 섞이면 안 된다."""
    ensure_schema(memory_db)
    _put(memory_db, financial=FIN_NA, news=NEWS_NA, classification=None)
    got = get_classification(memory_db, "battery", "KR", 2026, 3)
    assert got["financial_on"] is None and got["news_high"] is None
    assert got["classification"] is None


def test_꺼짐은_None이_아니라_False로_저장된다(memory_db):
    ensure_schema(memory_db)
    _put(memory_db, financial=FIN_OFF, news=NEWS_LOW, classification="관심 밖")
    got = get_classification(memory_db, "battery", "KR", 2026, 3)
    assert got["financial_on"] is False and got["news_high"] is False


def test_같은_분기를_다시_계산하면_갱신된다(memory_db):
    ensure_schema(memory_db)
    _put(memory_db, classification="조용한 변화", at="2026-10-01T00:00:00")
    _put(memory_db, financial=FIN_ON, news=NEWS_HIGH, classification="확인된 변화",
        at="2026-10-02T00:00:00")
    got = get_classification(memory_db, "battery", "KR", 2026, 3)
    assert got["classification"] == "확인된 변화" and got["computed_at"] == "2026-10-02T00:00:00"


def test_다른_분기_행은_건드리지_않는다(memory_db):
    """이력이 쌓인다 - 이번 분기를 갱신해도 지난 분기 값은 그대로다."""
    ensure_schema(memory_db)
    _put(memory_db, year=2026, quarter=2, classification="관심 밖")
    _put(memory_db, year=2026, quarter=3, classification="조용한 변화")
    assert get_classification(memory_db, "battery", "KR", 2026, 2)["classification"] == "관심 밖"
    assert get_classification(memory_db, "battery", "KR", 2026, 3)["classification"] == "조용한 변화"


def test_다른_테마_시장_분기는_섞이지_않는다(memory_db):
    ensure_schema(memory_db)
    _put(memory_db, theme_id="battery", market="KR", classification="조용한 변화")
    _put(memory_db, theme_id="battery", market="US", classification="관심 밖")
    _put(memory_db, theme_id="ai_semiconductor", market="KR", classification="확인된 변화")
    assert get_classification(memory_db, "battery", "KR", 2026, 3)["classification"] == "조용한 변화"
    assert get_classification(memory_db, "battery", "US", 2026, 3)["classification"] == "관심 밖"
    assert get_classification(memory_db, "ai_semiconductor", "KR", 2026, 3)["classification"] == "확인된 변화"


def test_테마_이력을_최신_분기부터_돌려준다(memory_db):
    ensure_schema(memory_db)
    for y, q in [(2025, 3), (2026, 1), (2025, 4), (2026, 2)]:
        _put(memory_db, year=y, quarter=q)
    got = [(r["fiscal_year"], r["fiscal_quarter"]) for r in get_theme_history(memory_db, "battery", "KR")]
    assert got == [(2026, 2), (2026, 1), (2025, 4), (2025, 3)]


def test_직전_분기_분류를_찾는다(memory_db):
    ensure_schema(memory_db)
    _put(memory_db, year=2026, quarter=2, classification="관심 밖")
    got = previous_classification(memory_db, "battery", "KR", 2026, 3)
    assert got["classification"] == "관심 밖"


def test_직전_분기가_연도를_넘어가도_찾는다(memory_db):
    ensure_schema(memory_db)
    _put(memory_db, year=2025, quarter=4, classification="기대 선행")
    got = previous_classification(memory_db, "battery", "KR", 2026, 1)
    assert got["classification"] == "기대 선행"


def test_직전_분기_기록이_없으면_None이다(memory_db):
    ensure_schema(memory_db)
    assert previous_classification(memory_db, "battery", "KR", 2026, 3) is None


# ── 운영 DB(Turso) 타입 ────────────────────────────────────────

def test_운영DB에서도_숫자와_불리언이_맞다(turso_like_db):
    ensure_schema(turso_like_db)
    _put(turso_like_db, financial=FIN_ON, news=NEWS_HIGH, classification="확인된 변화")
    got = get_classification(turso_like_db, "battery", "KR", 2026, 3)
    assert got["financial_on"] is True and isinstance(got["financial_on"], bool)
    assert got["news_high"] is True and isinstance(got["news_high"], bool)
    assert got["financial_changed"] == 3 and isinstance(got["financial_changed"], int)
    assert got["financial_ratio"] == 3 / 7 and isinstance(got["financial_ratio"], float)
    assert got["fiscal_year"] == 2026 and isinstance(got["fiscal_year"], int)


def test_운영DB에서도_데이터부족이_None으로_남는다(turso_like_db):
    ensure_schema(turso_like_db)
    _put(turso_like_db, financial=FIN_NA, news=NEWS_NA, classification=None)
    got = get_classification(turso_like_db, "battery", "KR", 2026, 3)
    assert got["financial_on"] is None and got["news_high"] is None and got["classification"] is None


def test_운영DB에서도_같은_분기_갱신이_된다(turso_like_db):
    ensure_schema(turso_like_db)
    _put(turso_like_db, classification="조용한 변화")
    _put(turso_like_db, classification="확인된 변화", financial=FIN_ON, news=NEWS_HIGH)
    got = get_classification(turso_like_db, "battery", "KR", 2026, 3)
    assert got["classification"] == "확인된 변화"


# ── 시장 유니버스 참고값 (5-1 화면 참고값) ────────────────────

def test_시장_참고값을_그대로_읽는다(memory_db):
    ensure_schema(memory_db)
    upsert_market_reference(memory_db, "KR", 2026, 3, 0.083, 412, "2026-10-01T00:00:00")
    got = get_market_reference(memory_db, "KR", 2026, 3)
    assert got["median_revenue_growth"] == pytest.approx(0.083) and got["sample_size"] == 412


def test_계산_불가면_None으로_저장된다(memory_db):
    """유니버스를 못 읽는 등으로 계산 불가일 때 - 0이 아니라 NULL이어야 한다."""
    ensure_schema(memory_db)
    upsert_market_reference(memory_db, "KR", 2026, 3, None, 0, "2026-10-01T00:00:00")
    got = get_market_reference(memory_db, "KR", 2026, 3)
    assert got["median_revenue_growth"] is None and got["sample_size"] == 0


def test_계산한_적_없으면_None이다(memory_db):
    ensure_schema(memory_db)
    assert get_market_reference(memory_db, "KR", 2026, 3) is None


def test_같은_분기_참고값도_다시_계산하면_갱신된다(memory_db):
    ensure_schema(memory_db)
    upsert_market_reference(memory_db, "KR", 2026, 3, 0.05, 400, "2026-10-01T00:00:00")
    upsert_market_reference(memory_db, "KR", 2026, 3, 0.09, 410, "2026-10-02T00:00:00")
    got = get_market_reference(memory_db, "KR", 2026, 3)
    assert got["median_revenue_growth"] == pytest.approx(0.09) and got["sample_size"] == 410


def test_시장끼리_참고값이_섞이지_않는다(memory_db):
    ensure_schema(memory_db)
    upsert_market_reference(memory_db, "KR", 2026, 3, 0.08, 400, "2026-10-01T00:00:00")
    upsert_market_reference(memory_db, "US", 2026, 3, 0.03, 500, "2026-10-01T00:00:00")
    assert get_market_reference(memory_db, "KR", 2026, 3)["median_revenue_growth"] == pytest.approx(0.08)
    assert get_market_reference(memory_db, "US", 2026, 3)["median_revenue_growth"] == pytest.approx(0.03)


def test_운영DB에서도_참고값_타입이_맞다(turso_like_db):
    ensure_schema(turso_like_db)
    upsert_market_reference(turso_like_db, "KR", 2026, 3, 0.083, 412, "2026-10-01T00:00:00")
    got = get_market_reference(turso_like_db, "KR", 2026, 3)
    assert isinstance(got["median_revenue_growth"], float) and isinstance(got["sample_size"], int)


def test_분류가_있던_행을_데이터부족으로_덮지_않는다(memory_db):
    """2026-11-17: 다시 계산했더니 뉴스 비율이 전부 None이라 9/23 분류가 NULL로 덮였다 - 화면용 표는 지키고 이력에만 쌓는다."""
    ensure_schema(memory_db)
    _put(memory_db, classification="조용한 변화", at="2026-09-23T12:29:44")
    _put(memory_db, financial=FIN_ON, news=NEWS_NA, classification=None, at="2026-11-17T05:26:46")
    got = get_classification(memory_db, "battery", "KR", 2026, 3)
    assert got["classification"] == "조용한 변화"
    rows = memory_db.execute("SELECT computed_at, classification FROM quarterly_theme_classification_history "
                             "ORDER BY computed_at").fetchall()
    assert [tuple(r) for r in rows] == [("2026-09-23T12:29:44", "조용한 변화"), ("2026-11-17T05:26:46", None)]


def test_원래_분류가_없으면_새_값으로_갱신한다(memory_db):
    ensure_schema(memory_db)
    _put(memory_db, financial=FIN_NA, news=NEWS_NA, classification=None, at="2026-09-23T00:00:00")
    _put(memory_db, financial=FIN_ON, news=NEWS_NA, classification=None, at="2026-11-17T00:00:00")
    got = get_classification(memory_db, "battery", "KR", 2026, 3)
    assert got["financial_on"] is True     # 둘 다 분류가 없으면 최신 숫자로
