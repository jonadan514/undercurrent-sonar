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


# ---- 코스피 투자자별 순매수 (2026-10-17) ----
def test_krw_flow_format_and_weekly_sum():
    assert g.fmt_krw_flow(3204e8) == "+3,204억" and g.fmt_krw_flow(-1.23e12) == "-1.2조" and g.fmt_krw_flow(None) == "-"
    rows = [{"date": f"2026-10-{d:02d}", "market": "KOSPI", "investor": "foreign", "value": 1e11} for d in range(6, 17)]
    s = g.sum_flows(rows)
    assert s["KOSPI"]["days"] == 5 and abs(s["KOSPI"]["foreign"] - 5e11) < 1 and s["KOSPI"]["to"] == "2026-10-16"
    assert g.sum_flows([]) is None


def test_foreign_flow_next_to_kospi():
    text = g.build_telegram_summary(_briefing(kr_flows={"KOSPI": {"foreign": 1.2e12, "days": 5}}))
    assert "🇰🇷 KOSPI -0.5% (외국인 +1.2조)" in text
    assert "외국인" not in g.build_telegram_summary(_briefing())


def test_earnings_week_window_and_tags():
    rows = [{"ticker": "MU", "market": "US", "earnings_date": "2026-10-21", "earnings_date_end": "2026-10-21", "is_estimate": 0},
            {"ticker": "005930", "market": "KR", "earnings_date": "2026-10-19", "earnings_date_end": "2026-10-23", "is_estimate": 1},
            {"ticker": "AAPL", "market": "US", "earnings_date": "2026-10-26", "earnings_date_end": "2026-10-26", "is_estimate": 0},
            {"ticker": "CNX", "market": "US", "earnings_date": "2026-10-18", "earnings_date_end": "2026-10-18", "is_estimate": 0}]
    ew = g.earnings_week_items(rows, "2026-10-19", {"US:MU": ["my", "turnaround"]}, {"KR:005930": "삼성전자"})
    assert [x["symbol"] for x in ew["items"]] == ["005930", "MU"]     # 다음 주(AAPL)·지난 일요일(CNX) 제외, 날짜순
    assert ew["by_market"] == {"KR": 1, "US": 1} and ew["tagged_count"] == 1
    assert ew["items"][0]["estimate"] and ew["items"][0]["name"] == "삼성전자"


def test_earnings_week_telegram():
    items = [{"market": "US", "symbol": f"T{i}", "name": None, "date": "2026-10-20", "date_end": "2026-10-20",
              "estimate": False, "tags": []} for i in range(10)]
    items.append({"market": "US", "symbol": "MU", "name": None, "date": "2026-10-21", "date_end": "2026-10-21",
                  "estimate": False, "tags": ["my", "turnaround"]})
    items.append({"market": "KR", "symbol": "005930", "name": "삼성전자", "date": "2026-10-22", "date_end": "2026-10-24",
                  "estimate": True, "tags": ["note"]})
    ew = {"total": 12, "by_market": {"US": 11, "KR": 1}, "tagged_count": 2, "items": items}
    text = g.build_telegram_summary(_briefing(earnings_week=ew))
    assert "이번 주 실적 발표</b> 🇺🇸 11 · 🇰🇷 1" in text
    assert "10/21 🇺🇸 MU · 내 관심 · 실적 반전" in text and "10/22(예상) 🇰🇷 삼성전자 · 노트" in text
    assert "T0" not in text and "외 10개" in text                     # 표시 종목만 먼저, 나머지는 건수
    ew2 = {**ew, "items": items[:10], "total": 10, "tagged_count": 0}
    assert "외 4개" in g.build_telegram_summary(_briefing(earnings_week=ew2))   # 표시 종목이 없으면 날짜 순 6개
    assert "실적 발표" not in g.build_telegram_summary(_briefing())
