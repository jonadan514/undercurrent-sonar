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
    assert "미국 시장 환경 흐름: 긴축 압력(첫 주만) → 위험 회피(마지막 주)" in facts
    assert "AI 반도체(미국) 소속 기업에 이달 생긴 일: Broadcom 내부자 매수" in facts
    assert "AI 반도체(미국) 가치사슬에서 소속 기업이 없는 구간: 기판" in facts
    assert any(f.startswith("트랩 필터 통과 목록: 한 달 사이 전체 규모가 늘었다. 새로 든 곳 예: Apple") for f in facts)
    assert "다음 달 실적 발표 - 내 워치리스트: Micron" in facts
    assert "관찰 노트 회고 - K-뷰티(한국): 적어 둔 기대 '뉴스↑' 빗나감" in facts
    assert not any(re.search(r"\d+\s*(%|개|종목)", f) for f in facts)


def test_regime_flow_and_ordinal():
    assert mr.regime_flow(["긴축 압력", "위험 회피", "위험 회피", "위험 회피"]) == "긴축 압력(첫 주만) → 위험 회피(이후 계속)"
    assert mr.regime_flow(["", "", ""]) == "뚜렷한 조합 없음(한 달 내내)"
    assert mr.regime_flow([]) == ""
    assert mr.ordinal_week(["2026-10-05", "2026-10-12"], "2026-10-12") == "둘째 주"


def test_tidy_name_drops_cut_suffix():
    assert mr.tidy_name("The Bank of New York Mellon Cor") == "The Bank of New York Mellon"
    assert mr.tidy_name("Carpenter Technology Corporatio") == "Carpenter Technology"
    assert mr.tidy_name("Nasdaq, Inc.") == "Nasdaq"
    assert mr.tidy_name("엘리스") == "엘리스"


def test_event_list_order_and_sentence_count():
    ev = {"US:BNY": ["실적 반전 목록에 새로 듦"], "KR:047040": ["큰 공급계약"], "US:GM": ["8-K 주의 공시", "내부자 매수"]}
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
