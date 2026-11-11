"""월간 보고서 조립(2026-11-07) - DB 읽기는 가짜로."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import generate_monthly_report as mr  # noqa: E402


def test_month_helpers():
    assert mr.month_range("2026-10") == (date(2026, 10, 1), date(2026, 11, 1))
    assert mr.month_range("2026-12") == (date(2026, 12, 1), date(2027, 1, 1))
    assert mr.prev_month(date(2026, 11, 2)) == "2026-10"
    assert mr.prev_month(date(2027, 1, 4)) == "2026-12"


def test_theme_section_labels_and_earn_turns(monkeypatch):
    rows = [
        {"theme_id": "k_beauty", "market": "KR", "week_start": "2026-10-05", "label": None, "news_arrow": "flat", "earn_arrow": "down", "price_arrow": "flat"},
        {"theme_id": "k_beauty", "market": "KR", "week_start": "2026-10-26", "label": "Quiet Strength", "news_arrow": "flat", "earn_arrow": "up2", "price_arrow": "flat"},
        {"theme_id": "game", "market": "KR", "week_start": "2026-10-05", "label": None, "news_arrow": "up1", "earn_arrow": "flat", "price_arrow": "up1"},
        {"theme_id": "game", "market": "KR", "week_start": "2026-10-26", "label": None, "news_arrow": "up1", "earn_arrow": "flat", "price_arrow": "up1"},
    ]
    monkeypatch.setattr(mr.wb, "turso_exec", lambda sql, args=None: rows)
    t = mr.theme_section(["2026-10-05", "2026-10-26"], {"k_beauty": "K-뷰티"})
    assert [x["theme"] for x in t["labeled"]] == ["K-뷰티"] and t["labeled"][0]["labels"][0]["label_ko"] == "숨은 강세"
    assert [(x["theme_id"], x["from"], x["to"]) for x in t["earn_turns"]] == [("k_beauty", "down", "up2")]


def test_month_events_and_summary_facts_have_no_numbers():
    import re
    bs = [{"insider_week": {"items": [{"market": "KR", "symbol": "000720", "buyers": 3, "all_plan": "0"}]},
           "kr_disclosures": {"contract": {"items": [{"symbol": "066970", "pct": 48}]}}}]
    ev = mr.month_events(bs)
    assert ev["KR:000720"] == ["내부자 여러 명 매수"] and ev["KR:066970"] == ["큰 공급계약"]
    r = {"regime": {"US": [{"combos": ["긴축 압력"]}, {"combos": ["위험 회피"]}], "KR": []},
         "themes": {"labeled": [{"theme": "K-뷰티", "market": "KR", "labels": [{"week": "2026-10-05", "label": "Quiet Strength"}]}], "earn_turns": []},
         "watchlist": {"watchlist": {"start_total": 360, "end_total": 380, "added": [{"symbol": "AAPL", "name": "Apple"}],
                                     "added_count": 3, "removed": [], "removed_count": 0}},
         "company_map": [{"theme": "AI 반도체", "market": "US", "groups": [
             {"n": 1, "label": "설계", "items": [{"name": "Broadcom", "events": ["내부자 매수"]}]},
             {"n": 2, "label": "기판", "items": []}]}],
         "reviews": [{"target": "K-뷰티", "market": "KR", "results": [{"expect": "뉴스↑", "hit": False}]}],
         "calendar": {"earnings": [{"name": "Micron", "tags": ["내 관심"]}], "deadlines": []}}
    facts = mr.summary_facts(r)
    assert "미국 시장 환경: 첫째 주에는 '긴축 압력'이 붙었고, 둘째 주에는 '위험 회피'가 붙었다" in facts
    assert "AI 반도체(미국) 소속 기업에 이달 생긴 일: Broadcom 내부자 매수" in facts
    assert "AI 반도체(미국) 가치사슬에서 소속 기업이 없는 구간: 기판" in facts
    assert any(f.startswith("트랩 필터 통과 목록: 한 달 사이 전체 규모가 늘었다. 새로 든 곳 예: Apple") for f in facts)
    assert "다음 달 실적을 발표하는 내 워치리스트 종목: Micron" in facts
    assert "관찰 노트 회고 - 한국 K-뷰티: '뉴스가 늘 것'이라고 적어 둔 기대가 빗나갔다(뉴스는 늘지 않았다)" in facts
    assert not any(re.search(r"\d+\s*(%|개|종목)", f) for f in facts)


def test_regime_flow_and_ordinal():
    assert mr.regime_flow(["긴축 압력", "위험 회피", "위험 회피", "위험 회피"]) == "첫째 주에는 '긴축 압력'이 붙었고, 둘째 주부터 '위험 회피'가 이어졌다"
    assert mr.regime_flow(["", "위험 회피", "위험 회피"]) == "첫째 주에는 뚜렷한 조합이 없었고, 둘째 주부터 '위험 회피'가 이어졌다"
    assert mr.regime_flow(["위험 선호", "위험 선호", "긴축 압력"]) == "첫째 주부터 둘째 주까지 '위험 선호'가 이어졌고, 셋째 주에는 '긴축 압력'이 붙었다"
    assert mr.regime_flow(["", "", ""]) == "한 달 내내 뚜렷한 조합이 없었다"
    assert mr.regime_flow([]) == ""
    assert mr.ordinal_week(["2026-10-05", "2026-10-12"], "2026-10-12") == "둘째 주"


def test_tidy_name_drops_cut_suffix():
    assert mr.tidy_name("The Bank of New York Mellon Cor") == "The Bank of New York Mellon"
    assert mr.tidy_name("Carpenter Technology Corporatio") == "Carpenter Technology"
    assert mr.tidy_name("Nasdaq, Inc.") == "Nasdaq"
    assert mr.tidy_name("엘리스") == "엘리스"


def test_event_list_order_and_sentence_count():
    ev = {"US:BNY": ["실적 반전 목록에 새로 오름"], "KR:047040": ["큰 공급계약"], "US:GM": ["8-K 주의 공시", "내부자 매수"]}
    out = mr.event_list(ev, {"US:GM": "General Motors"})
    assert [x["symbol"] for x in out] == ["GM", "047040", "BNY"] and out[0]["name"] == "General Motors"
    assert mr.sentence_count("가였다. 나였다. 다였다.") == 3 and mr.sentence_count("") == 0


def test_repeat_endings():
    assert mr.repeat_endings("가가 맞았다. 나나 맞았다. 다다로 돌아섰다.") == 1
    assert mr.repeat_endings("가가 맞았다.\n\n나나 맞았다.") == 0


def test_advice_titles_not_passed_to_summary():
    assert mr._ADVICE_RE.search("K뷰티 주가 조정 끝물?…'이 기업' 저가매수 기회")
    assert mr._ADVICE_RE.search("Semiconductor Sell-Off: The 1 AI Chip Stock I'd Buy and 1 I'd Avoid")
    assert not mr._ADVICE_RE.search("금호석유화학그룹, R&D 사활…고부가 소재·배터리 만든다")
    assert not mr._ADVICE_RE.search("Consumer AI agents could upend online shopping")


def test_drop_eval_and_missing():
    assert mr._drop_eval("가가 예정돼 있다. 나나도 주목할 일정이다.") == "가가 예정돼 있다."
    assert mr.missing_names("조선과 방산", ["조선", "방산", "재생에너지"]) == ["재생에너지"]


def test_review_sentence_and_market_split():
    assert mr.review_sentence("theme", {"expect": "실적↑ 유지", "hit": True}) == "'실적 개선이 이어질 것'이라고 적어 둔 기대가 맞았다(실제로 실적 개선이 이어졌다)"
    assert mr.review_sentence("theme", {"key": "news_up", "hit": None}).endswith("판단하지 못했다")
    r = {"regime": {}, "themes": {"labeled": [{"theme": "K-뷰티", "market": "KR", "labels": [{"week": "w", "label": "Quiet Strength"}]},
                                                {"theme": "AI 소프트웨어", "market": "US", "labels": [{"week": "w", "label": "Quiet Strength"}]}],
                                   "earn_turns": [{"theme": "조선", "market": "KR", "from": "flat", "to": "up1"}]},
         "watchlist": {}, "reviews": [], "calendar": {}}
    f = mr.summary_facts(r)
    kr, us = f.index("[테마 - 한국]"), f.index("[테마 - 미국]")
    assert kr < next(i for i, x in enumerate(f) if x.startswith("한국 조선 실적(소속 기업 실적 흐름): 월초 보합 → 월말 오름")) < us < next(i for i, x in enumerate(f) if x.startswith("미국 AI 소프트웨어"))


def test_market_lead():
    W = [{"combos": ["긴축 압력"]}, {"combos": ["위험 회피"]}, {"combos": ["위험 회피"]}]
    K = [{"combos": []}, {"combos": ["위험 회피"]}, {"combos": ["위험 회피"]}]
    assert mr.market_lead({"regime": {"US": W, "KR": K}}) == (
        "이달 미국 시장은 첫째 주 '긴축 압력'에서 둘째 주부터 '위험 회피'로 바뀌었고, "
        "한국 시장은 첫째 주에는 뚜렷한 조합이 없다가 둘째 주부터 '위험 회피'가 이어졌다.")
    assert mr.market_lead({"regime": {"US": K, "KR": K}}).startswith("이달 미국과 한국 시장은 모두 첫째 주에는")
    assert mr.lead_flow(["위험 회피", "위험 회피", "긴축 압력"]) == "첫째 주부터 둘째 주까지 '위험 회피'에서 셋째 주에 '긴축 압력'으로 바뀌었다"
    assert mr.market_lead({"regime": {}}) == ""


def test_when_in_month():
    W = ["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"]
    assert mr.when_in_month(W, "2026-10-26") == "월말(넷째 주)"
    assert mr.when_in_month(W, "2026-10-05") == "월초(첫째 주)"
    assert mr.when_in_month(W, "2026-10-12") == "월중(둘째 주)"


def test_verbatim_titles():
    t = ["패키지도 그대로 베껴… K뷰티 ‘짝퉁’ 대응 나섰다", "짧은 제목"]
    assert mr.verbatim_titles("'패키지도 그대로 베껴… K뷰티 ‘짝퉁’ 대응 나섰다'가 있었다", t) == 1
    assert mr.verbatim_titles("짝퉁 대응을 다룬 기사가 나왔다", t) == 0


def test_missing_names_same_sentence():
    t = "AI 반도체는 실적이 올랐다. 방산에서는 탄약 구간이 비어 있다."
    assert mr.missing_names(t, ["방산|실적", "AI 반도체|실적"]) == ["방산"]
    assert mr.missing_names("방산은 소속 기업 실적이 월초 오름에서 월말 보합으로 돌아섰다.", ["방산|실적"]) == []


SEPT_FACTS = ["[워치리스트·회고]", "트랩 필터 통과 목록: 한 달 사이 전체 규모가 늘었다. 새로 든 곳 예: 유한양행, KCC / 빠진 곳 예: 없음",
              "[다음 달]", "다음 달 실적을 발표하는 후보 중 테마 소속 기업: Mueller Industries, 현대로템"]


def test_ungrounded_catches_invented_themes_and_reviews():
    """9월 소급 미리보기(2026-11-11)에서 지어낸 테마·회고 문장을 잡는다 - 사실 본문에 있는 이름은 통과."""
    from generate_monthly_report import drop_ungrounded, ungrounded
    text = ("한국의 K-뷰티와 바이오테크 분야에서는 실적 개선 기대가 있었다. 유한양행과 KCC가 새로 목록에 올랐다.\n\n"
            "관찰 노트 회고 결과 기대가 맞았다. 다음 달에는 현대로템의 실적 발표가 예정돼 있다.")
    assert ungrounded(text, SEPT_FACTS) == ["K-뷰티", "관찰 노트", "기대가 맞", "바이오", "뷰티", "회고"]
    out = drop_ungrounded(text, SEPT_FACTS)
    assert out == "유한양행과 KCC가 새로 목록에 올랐다.\n\n다음 달에는 현대로템의 실적 발표가 예정돼 있다."
    facts = SEPT_FACTS + ["[테마 - 한국]", "한국 K-뷰티 실적(소속 기업 실적 흐름): 월초 보합 → 월말 오름 - 주가가 아니라 실적 이야기"]
    assert ungrounded("한국의 K-뷰티는 소속 기업 실적이 오름으로 돌아섰다.", facts) == []


def test_paragraph_specs_only_for_present_groups():
    from generate_monthly_report import paragraph_specs
    specs = paragraph_specs(SEPT_FACTS)
    assert len(specs) == 2 and "워치리스트" in specs[0] and "기업 지도" not in specs[0]
    assert "다음 달" in specs[1] and "회고" not in specs[1]
