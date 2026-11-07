"""주간 총평 '이번 주 짚을 점'(2026-11-02) - 칸 사이의 겹침·엇갈림을 코드가 고른다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzers import briefing_points as bp  # noqa: E402
import scripts.generate_weekly_briefing as g  # noqa: E402


def _b(**kw):
    b = {"watchlist": {"has_prev": True, "added": [], "removed": []}, "turnaround": {"added": []}, "sentiment_heating": [],
         "kr_disclosures": {}, "insider_week": {}, "us_8k_week": {}, "earnings_week": {}, "theme_labels": {},
         "observation_reviews": [], "macro": {}}
    b.update(kw)
    return b


def test_mixed_and_aligned_and_plan_insider_ignored():
    b = _b(sentiment_heating=[{"market": "KR", "symbol": "008930", "name": "한미사이언스", "path": "낮음→높음"},
                              {"market": "KR", "symbol": "042660", "name": "한화오션", "path": "보통→높음"},
                              {"market": "KR", "symbol": "005690", "name": "파미셀", "path": "낮음→보통"}],
           kr_disclosures={"prelim": {"items": [
               {"symbol": "008930", "name": "한미사이언스", "operating_income_yoy_pct": -51.3, "revenue_yoy_pct": 5.9},
               {"symbol": "042660", "name": "한화오션", "operating_income_yoy_pct": 67.6, "revenue_yoy_pct": 12.9},
               {"symbol": "000660", "name": "SK하이닉스", "operating_income_yoy_pct": 632, "revenue_yoy_pct": 328}]}},
           insider_week={"items": [{"market": "KR", "symbol": "000660", "name": "SK하이닉스", "buyers": 1, "all_plan": True}]})
    pts = bp.find_points(b, {}, {}, set())
    kinds = {p["title_name"]: p["kind"] for p in pts}
    assert kinds["한미사이언스"] == "mixed" and kinds["한화오션"] == "aligned"
    assert "SK하이닉스" not in kinds and "파미셀" not in kinds          # 계획 매수만 / 관심도 하나만이면 점이 아니다
    assert pts[0]["title"] == "한미사이언스 · 신호가 엇갈림"           # 엇갈림이 같은 방향 겹침보다 먼저
    assert "잠정실적 영업이익 크게 줄어듦(전년 같은 분기 대비)" in pts[0]["facts"]


def test_mine_first_and_warn():
    b = _b(kr_disclosures={"termination": {"items": [{"symbol": "445680", "name": "큐리옥스바이오시스템즈"}]},
                           "prelim": {"items": [{"symbol": "445680", "name": "큐리옥스바이오시스템즈", "operating_income_yoy_turn": "적자지속"}]}},
           us_8k_week={"items": [{"symbol": "GM", "items": [{"item": "3.01", "label": "상장 유지 기준 미달·이전", "warn": True}]}]},
           earnings_week={"items": [{"market": "US", "symbol": "GM", "date": "2026-11-04"}]},
           turnaround={"added": [{"market": "US", "symbol": "GM", "name": "GM"}]})
    pts = bp.find_points(b, {}, {}, {"US:GM"}, g.COMMENT_8K)
    assert [p["kind"] for p in pts] == ["mine", "warn"]
    assert any("상장 관련 통지" in f for f in pts[0]["facts"]) and "이번 주 실적 발표 예정(2026-11-04)" in pts[0]["facts"]


def test_theme_review_macro_and_members():
    b = _b(theme_labels={"new_labels": [{"theme_id": "k_beauty", "label": "Quiet Strength", "market": "KR"},
                                        {"theme_id": "lng_gas", "label": "Overheated Buzz", "market": "US"},
                                        {"theme_id": "game", "label": "Early Buzz", "market": "KR"}]},
           observation_reviews=[{"kind": "theme", "market": "KR", "theme_id": "k_beauty", "checkpoint": "4", "expect_results": {"news_up": False}},
                                {"kind": "theme", "market": "US", "theme_id": "infra", "checkpoint": "4", "expect_results": {}},
                                {"kind": "theme", "market": "KR", "theme_id": "ai_semi", "checkpoint": "4", "expect_results": {"earn_hold": True}}],
           macro={"natgas": {"value": 2.91, "chg_1w": 0.31}},
           kr_disclosures={"contract": {"items": [{"symbol": "111", "name": "코스맥스", "pct": 12}]}})
    pts = bp.find_points(b, {"k_beauty": "K-뷰티", "lng_gas": "천연가스·LNG", "game": "게임"},
                         {("KR", "k_beauty"): {"111"}}, set(), qual_macro=g.qual_macro)
    by = {p["title"]: p for p in pts}
    kb = by["K-뷰티 테마 · 관찰 노트 회고"]
    assert kb["kind"] == "review"
    assert "한국 관찰 노트(4주 전): '뉴스가 늘 것'이라 봤는데 그렇게 되지 않음" in kb["facts"]
    assert "한국 소속 종목 중 이번 주 신호: 코스맥스: 매출 대비 큰 공급계약" in kb["facts"]   # 시장을 앞에(2026-11-05)
    assert "같은 주 천연가스 가격 1주 큰 폭 상승" in by["천연가스·LNG 테마"]["facts"]
    assert "게임 테마" not in by                                  # 라벨 하나뿐이고 이어지는 게 없으면 뺀다
    assert not any("infra" in t for t in by)                      # 기대도 안 적고 이어지는 것도 없는 회고는 뺀다
    assert by["ai_semi 테마 · 관찰 노트 회고"]["kind"] == "review_plain"
    # 소속 종목 신호로만 이어지는 노트는 라벨·매크로로 이어지는 노트보다 뒤, 다른 시장 종목은 잇지 않는다
    b2 = _b(observation_reviews=[{"kind": "theme", "market": "US", "theme_id": "infra", "checkpoint": "4", "expect_results": {}},
                                 {"kind": "theme", "market": "KR", "theme_id": "ai_semi", "checkpoint": "4", "expect_results": {"earn_hold": True}}],
            kr_disclosures={"prelim": {"items": [{"symbol": "000660", "name": "SK하이닉스", "operating_income_yoy_pct": 600},
                                                 {"symbol": "047040", "name": "대우건설", "operating_income_yoy_pct": 224}]}})
    p2 = bp.find_points(b2, {}, {("KR", "infra"): {"047040"}, ("KR", "ai_semi"): {"000660"}}, set())
    assert [(p["title"], p["kind"]) for p in p2] == [("ai_semi 테마 · 관찰 노트 회고", "review_members")]
    order = [p["kind"] for p in pts]
    assert order == sorted(order, key=bp.PRIORITY.index)


def test_caps():
    heat = [{"market": "KR", "symbol": str(i), "name": f"종목{i}", "path": "낮음→높음"} for i in range(6)]
    prelim = [{"symbol": str(i), "name": f"종목{i}", "operating_income_yoy_pct": -40} for i in range(6)]
    pts = bp.find_points(_b(sentiment_heating=heat, kr_disclosures={"prelim": {"items": prelim}}), {}, {}, set())
    assert len(pts) == bp.MAX_STOCK_POINTS


def test_assemble_comment_titles_fallback_and_cleanup():
    pts = [{"title": "한미사이언스 · 신호가 엇갈림", "title_name": "한미사이언스", "facts": ["관심도 상승(낮음→높음)", "잠정실적 영업이익 크게 줄어듦"]},
           {"title": "천연가스·LNG 테마", "facts": ["미국: '기대 과열' 라벨이 새로 붙음"]}]
    out = g.assemble_comment("지수는 엇갈렸습니다. 기관 매수가 지수에 긍정적인 영향을 줬습니다.",
                             [{"body": "한미사이언스는 관심이 올랐지만 영업이익은 크게 줄었습니다. 영업이익이 51% 줄었습니다.",
                               "next": "다음 분기 영업이익이 관심도를 따라가는지."}], pts)
    assert out == ("■ 시장 분위기\n지수는 엇갈렸습니다.\n\n"
                   "■ 한미사이언스 · 신호가 엇갈림\n한미사이언스는 관심이 올랐지만 영업이익은 크게 줄었습니다.\n"
                   "→ 이어서 볼 것: 다음 분기 영업이익이 관심도를 따라가는지\n\n"
                   "■ 천연가스·LNG 테마\n미국: '기대 과열' 라벨이 새로 붙음.")   # 본문이 모자라면 사실을 그대로 잇는다


def test_label_meaning_attached_and_markets_differ():
    # 11/2 미리 보기: 미국 동반 상승·한국 숨은 강세를 GPT가 "두 시장 모두 주가가 올랐다"로 섞었다 - 뜻을 시장별 문장에 붙이고 차이를 적는다
    b = _b(theme_labels={"new_labels": [{"theme_id": "petro", "label": "Full Alignment", "market": "US"},
                                        {"theme_id": "petro", "label": "Quiet Strength", "market": "KR"}]})
    p = bp.find_points(b, {"petro": "석유화학"}, {}, set())[0]
    assert p["facts"][:3] == ["미국: '동반 상승' 라벨이 새로 붙음 - 뉴스·실적·주가가 모두 오름",
                              "한국: '숨은 강세' 라벨이 새로 붙음 - 실적은 크게 좋아졌는데 뉴스는 조용하고 주가도 아직 그대로",
                              "같은 테마인데 미국과 한국의 라벨이 다름 - 두 시장을 따로 봐야 함"]



def test_strip_interpretive_closing():
    assert g.strip_speculation("■ 테마\n실적이 먼저 움직였다. 이는 시장의 관심이 부족함을 보여준다.") == "■ 테마\n실적이 먼저 움직였다."


def test_fix_passive():
    assert g.fix_passive("뉴스는 조용해 '숨은 강세'로 분류됐다.") == "뉴스는 조용해 '숨은 강세' 라벨이 붙었다."


def test_fix_passive_more():
    assert g.fix_passive("미국 시장은 하락세를 보인 반면 한국은 올랐다.") == "미국 시장은 하락한 반면 한국은 올랐다."
    assert g.fix_passive("미국의 경우 뉴스가 늘었다. 한국의 경우, 조용했다.") == "미국은 뉴스가 늘었다. 한국은 조용했다."

    assert g.fix_passive("달러인덱스는 보합세를 보였다.") == "달러인덱스는 보합이었다."


def test_fix_passive_drops_evaluative_tail():
    assert g.fix_passive("Intel의 내부자 매수도 주목할 만하다.") == "Intel의 내부자 매수도 있었다."
    assert g.fix_passive("실적이 눈에 띈다.") == "실적이 눈에 띈다."


def test_prelim_profit_up_revenue_down_is_mixed():
    """영업이익과 매출이 반대 방향이면 '같은 방향'이 아니라 '엇갈림'(2026-11-05, 11/9 미리 보기 현대건설)."""
    b = _b(kr_disclosures={"prelim": {"items": [{"symbol": "000720", "name": "현대건설", "operating_income_yoy_pct": 120,
                                                 "revenue_yoy_pct": -15}]}},
           insider_week={"items": [{"market": "KR", "symbol": "000720", "name": "현대건설", "buyers": 3, "all_plan": False}]})
    pts = bp.find_points(b, {}, {}, set())
    p = next(x for x in pts if x["symbol"] == "000720")
    assert p["kind"] == "mixed"
    assert "잠정실적 매출 줄어듦(전년 같은 분기 대비)" in p["facts"]
    # 같은 방향이면 예전처럼 한 줄
    s = bp.stock_signals(_b(kr_disclosures={"prelim": {"items": [{"symbol": "1", "name": "A", "operating_income_yoy_pct": 40,
                                                                    "revenue_yoy_pct": 20}]}}))
    assert [t for _, _, t in s[("KR", "1")]["signals"]] == ["잠정실적 영업이익 크게 늘어남(전년 같은 분기 대비), 매출 늘어남"]


def test_strip_speculation_interpretive_closings():
    t = "롯데정밀화학은 영업이익이 줄었지만 매출은 늘었다. 이는 주목할 만한 변화이다."
    assert g.strip_speculation(t) == "롯데정밀화학은 영업이익이 줄었지만 매출은 늘었다."
    assert g.strip_speculation("현대건설의 매출 감소가 실적에 미칠 영향이 지속될지") == ""


def test_comment_style_checks():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import generate_weekly_briefing as wb
    t = "■ 시장 분위기\n가가 맞았다. 나나 맞았다. 다다로 돌아섰다.\n→ 이어서 볼 것: 라라가 이어질지"
    assert wb.repeat_endings(t) == 1
    assert wb.strip_speculation("Apple 실적 발표도 주목할 일정이다. 조선은 실적이 올랐다.") == "조선은 실적이 올랐다."
    assert wb.strip_speculation("가나테마는 시장의 주목을 받았다. 실적이 늘었다.") == "실적이 늘었다."
    assert wb.verbatim_titles("'패키지도 그대로 베껴… K뷰티 짝퉁' 기사", ["패키지도 그대로 베껴… K뷰티 ‘짝퉁’ 대응 나섰다"]) == 1
