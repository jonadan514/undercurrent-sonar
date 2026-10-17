"""주간 브리핑 텔레그램 본문 (2026-10-05 정리분) - 건수·이스케이프·라벨 없음 안내."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "generate_weekly_briefing", Path(__file__).resolve().parent.parent / "scripts" / "generate_weekly_briefing.py")
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)


def _briefing(**over):
    b = {"week": "2026-10-12", "us": {"index_chg_1w": 1.2}, "kr": {"index_chg_1w": -0.5},
         "macro": {"us10y": {"value": 4.1234, "chg_1w": 0.0812}, "usdkrw": {"value": 1386.4, "chg_1w": -12.3}},
         "watchlist": {"total": 275, "added": [{"market": "KR", "symbol": str(i), "name": f"종목{i}"} for i in range(10)],
                       "removed": [], "added_count": 27, "removed_count": 0, "has_prev": True},
         "sentiment_heating": [], "theme_labels": {"week_start": "2026-10-05", "new_labels": [],
                                                   "label_counts": {"US": 0, "KR": 0}}}
    b.update(over)
    return b


def test_counts_use_full_total_not_truncated_list():
    text = g.build_telegram_summary(_briefing())
    assert "신규 27" in text and "외 24개" in text


def test_names_are_html_escaped():
    wl = {"total": 1, "added": [{"market": "KR", "symbol": "383220", "name": "F&F"}], "removed": [],
          "added_count": 1, "removed_count": 0, "has_prev": True}
    text = g.build_telegram_summary(_briefing(watchlist=wl))
    assert "F&amp;F" in text and "F&F" not in text


def test_theme_radar_line_always_present():
    assert "아직 라벨 없음" in g.build_telegram_summary(_briefing())
    assert "테마 신호 데이터 없음" in g.build_telegram_summary(_briefing(theme_labels={}))


def test_macro_line_and_no_gpt():
    text = g.build_telegram_summary(_briefing(gpt_comment="지수가 3% 올랐다"))
    assert "미 10년물 4.12% (+0.08%p)" in text and "원/달러 1,386원 (-12원)" in text
    assert "3% 올랐다" not in text          # GPT 총평은 웹에만
    assert "금리·환율" not in g.build_telegram_summary(_briefing(macro=None))


def test_no_double_blank_lines():
    text = g.build_telegram_summary(_briefing(us={}, kr={}, macro=None))
    assert "\n\n\n" not in text


def test_observation_reviews_line():
    rv = [{"kind": "theme", "market": "KR", "theme_id": "ai_semiconductor", "ticker": None, "checkpoint": 4,
           "expect_results": {"news_up": True, "price_up": None}}]
    text = g.build_telegram_summary(_briefing(observation_reviews=rv))
    assert "관찰 노트 회고 도착" in text and "4주 전" in text
    assert "뉴스↑ 일어남" in text and "주가↑ 판단 불가" in text
    assert "관찰 노트" not in g.build_telegram_summary(_briefing())


def test_kr_treasury_in_rates_line():
    m = {"us10y": {"value": 4.12, "chg_1w": 0.08}, "kr3y": {"value": 3.937, "chg_1w": -0.051},
         "usdkrw": {"value": 1386.4, "chg_1w": -12.3}}
    text = g.build_telegram_summary(_briefing(macro=m))
    assert "미 10년물 4.12% (+0.08%p) · 국고채 3년 3.94% (-0.05%p) · 원/달러 1,386원 (-12원)" in text


def test_dxy_and_wti_in_rates_line():
    m = {"us10y": {"value": 4.12, "chg_1w": 0.08}, "usdkrw": {"value": 1386.4, "chg_1w": -12.3},
         "dxy": {"value": 99.84, "chg_1w": 0.62}, "wti": {"value": 61.5, "chg_1w": -1.5}}
    text = g.build_telegram_summary(_briefing(macro=m))
    # 61.5 - (-1.5) = 63.0 -> -1.5/63.0 = -2.4%
    assert "금리·환율·유가 미 10년물 4.12% (+0.08%p) · 원/달러 1,386원 (-12원) · 달러인덱스 99.8 (+0.6) · WTI $61.5 (-2.4%)" in text
    # 유가가 없으면 예전 이름 그대로
    m2 = {k: v for k, v in m.items() if k != "wti"}
    assert "금리·환율 미 10년물" in g.build_telegram_summary(_briefing(macro=m2))


# ---- 실적 반전 주간 변동 (2026-10-17) ----
def _c(m, s, g, ttm=None, q=None, ttm_yoy=None, q_yoy=None, name=None):
    return {"market": m, "symbol": s, "name": name, "growth_tier": g, "rev_ttm_tier": ttm, "rev_ttm_yoy": ttm_yoy,
            "rev_q_tier": q, "rev_q_yoy": q_yoy}


def test_turnaround_rule_matches_watchlist_button():
    assert g.is_turnaround(_c("KR", "005930", "정체", ttm="성장", q="성장"))
    assert not g.is_turnaround(_c("KR", "A", "정체", ttm="정체", q="성장"))   # 1년이 있으면 1년 기준
    assert g.is_turnaround(_c("US", "MU", "역성장", ttm=None, q="성장"))       # 1년 없으면 분기
    assert not g.is_turnaround(_c("US", "B", "성장", ttm="성장"))              # 3년도 성장이면 반전 아님


def test_turnaround_diff_and_telegram_lines():
    cur = [_c("KR", "005930", "정체", ttm="성장", ttm_yoy=0.572, name="삼성전자"),
           _c("US", "MU", "정체", ttm="성장", ttm_yoy=1.1), _c("US", "AAPL", "정체", ttm="정체")]
    first = g.turnaround_diff(cur, None)
    assert first["total"] == 2 and first["by_market"] == {"KR": 1, "US": 1} and not first["has_prev"]
    d = g.turnaround_diff(cur, [{"market": "US", "symbol": "MU"}, {"market": "US", "symbol": "OLD"}])
    assert d["added_count"] == 1 and d["added"][0]["symbol"] == "005930" and d["removed_count"] == 1
    d.pop("items")
    text = g.build_telegram_summary(_briefing(turnaround=d))
    assert "🔄 실적 반전</b> 🇺🇸 1 · 🇰🇷 1 · 새로 1 · 빠짐 1" in text and "삼성전자 1년 +57%" in text
    first.pop("items")
    assert "다음 주부터" in g.build_telegram_summary(_briefing(turnaround=first))
    assert "실적 반전" not in g.build_telegram_summary(_briefing())
