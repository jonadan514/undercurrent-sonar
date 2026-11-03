"""짚을 점 관련 기사 고르기(2026-11-03)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzers.briefing_news import clean_title, pick_headlines  # noqa: E402


def _r(t, d="2026-10-28", src="한경", url=None):
    return {"title": t, "url": url or f"https://x/{abs(hash(t))}", "source": src, "published_at": d}


def test_clean_title_strips_google_source_suffix():
    assert clean_title("K-뷰티 수출 사상 최대 - 한국경제", "한국경제") == "K-뷰티 수출 사상 최대"
    assert clean_title("LNG carriers in demand - Reuters") == "LNG carriers in demand"
    assert clean_title("코스맥스 3분기 실적 호조") == "코스맥스 3분기 실적 호조"


def test_priority_dedupe_and_limit():
    rows = [_r("화장품 업계 동향 전반 정리", "2026-10-31"),
            _r("코스맥스, 美 공장 증설 착수", "2026-10-27"),
            _r("코스맥스 미국 공장 증설 착수", "2026-10-29"),     # 거의 같은 제목 - 하나만
            _r("아모레퍼시픽 신제품 출시 소식", "2026-10-30"),
            _r("짧음"),                                            # 너무 짧은 제목은 버림
            _r("K-뷰티 수출 호조 이어져", "2026-11-01")]
    out = pick_headlines(rows, ["코스맥스"], ["아모레퍼시픽", "코스맥스"])
    assert [o["title"] for o in out] == ["코스맥스 미국 공장 증설 착수", "아모레퍼시픽 신제품 출시 소식", "K-뷰티 수출 호조 이어져"]


def test_must_contain_for_stock_search():
    rows = [_r("한미사이언스 임시주총 결과"), _r("제약주 전반 약세 흐름 정리")]
    assert [o["title"] for o in pick_headlines(rows, ["한미사이언스"], must_contain="한미사이언스")] == ["한미사이언스 임시주총 결과"]


def test_keyword_tier_and_opinion_filter():
    # 11/3 미리 보기: 천연가스 테마에 Chevron 부채·"42% Undervalued"가 뽑혔다 - 키워드 기사 우선, 투자 의견 제목은 뺀다
    rows = [_r("Chevron Halved Its Net Debt in Six Months", "2026-11-01", "Yahoo"),
            _r("Targa Resources (TRGP) Stock Could Be 42% Undervalued On Cash Flow", "2026-11-01", "Yahoo"),
            _r("US LNG exports hit record as new terminal ramps up", "2026-10-29", "www.reuters.com"),
            _r("삼성전자도 SK하이닉스도 아니다…기관이 한달간 순매수한 '1위 주식'", "2026-11-01")]
    out = pick_headlines(rows, [], ["Chevron", "Targa Resources", "SK하이닉스"], keywords=["LNG", "natural gas"])
    assert [o["title"] for o in out] == ["US LNG exports hit record as new terminal ramps up", "Chevron Halved Its Net Debt in Six Months"]
    assert out[0]["source"] == "reuters.com"


def test_long_title_cut_and_watching_filtered():
    long = "Live On CNBC, Chevron CEO Says " + "and more words " * 10
    out = pick_headlines([_r(long), _r("3 U.S. Natural Gas Stocks Worth Watching As LNG Demand Builds")])
    assert len(out) == 1 and out[0]["title"].endswith("…") and len(out[0]["title"]) <= 91
