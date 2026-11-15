"""브리핑 '이번 주 볼 것'(2026-11-15) - 라벨 테마, 없으면 '실적↑↑·주가 아직', 후보는 테마 소속 + 이번 주 이유."""
from src.analyzers.week_focus import INTERIM_WHY, focus_stocks, focus_themes, week_reasons

NAMES = {"ship": "조선", "beauty": "K-뷰티", "ai": "AI 반도체", "grid": "전력망"}
ROWS = [
    {"market": "KR", "theme_id": "beauty", "label": "Full Alignment", "news": "up1", "earn": "up1", "price": "up1"},
    {"market": "KR", "theme_id": "ship", "label": "Quiet Strength", "news": "flat", "earn": "up2", "price": "flat"},
    {"market": "KR", "theme_id": "grid", "label": None, "news": "flat", "earn": "up2", "price": "down"},
    {"market": "US", "theme_id": "ai", "label": None, "news": "flat", "earn": "up2", "price": "flat"},
]


def test_themes_labels_first_then_interim():
    t = focus_themes(ROWS, NAMES)
    assert [(x["market"], x["theme_id"]) for x in t] == [("US", "ai"), ("KR", "ship"), ("KR", "beauty")]
    assert t[0]["why"] == INTERIM_WHY and t[1]["label"] == "Quiet Strength"


def test_stocks_need_theme_and_reason_and_focus_first():
    b = {"watchlist": {"added_keys": ["KR:009540", "KR:000001"]},
         "insider_week": {"items": [{"market": "KR", "symbol": "010140", "buyers": 2, "all_plan": False}]}}
    cands = [{"market": "KR", "symbol": "009540", "name": "HD한국조선해양"},
             {"market": "KR", "symbol": "010140", "name": "삼성중공업"},
             {"market": "KR", "symbol": "000001", "name": "테마밖"},
             {"market": "KR", "symbol": "123456", "name": "가나다", "valuation_tier": "싼 편", "growth_tier": "성장"}]
    members = {("KR", "ship"): {"010140"}, ("KR", "grid"): {"009540", "123456"}}
    themes = focus_themes(ROWS, NAMES)
    stocks, total = focus_stocks(b, cands, members, themes, NAMES)
    assert total["KR"] == 3                                     # 테마 밖 000001은 빠진다
    assert stocks[0]["symbol"] == "010140" and stocks[0]["in_focus"] and stocks[0]["reasons"] == ["내부자 여러 명 매수"]
    assert {s["symbol"] for s in stocks} == {"010140", "009540", "123456"}
    assert week_reasons(b, cands)["KR:123456"] == ["밸류 LOW·성장"]
