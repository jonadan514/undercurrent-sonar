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


def test_kr_notice_overrides_yfinance_date():
    rows = [{"ticker": "128940", "market": "KR", "earnings_date": "2026-10-30", "earnings_date_end": "2026-11-03", "is_estimate": 1},
            {"ticker": "MU", "market": "US", "earnings_date": "2026-10-21", "earnings_date_end": "2026-10-21", "is_estimate": 0}]
    merged = g.merge_kr_notices(rows, [{"ticker": "128940", "announce_date": "2026-10-27"},
                                       {"ticker": "263750", "announce_date": None}], "2026-10-26")
    ew = g.earnings_week_items(merged, "2026-10-26", {}, {})
    assert [(x["symbol"], x["date"], x["estimate"]) for x in ew["items"]] == [("128940", "2026-10-27", False)]


def _disc(no, code, name, kind, payload, dt="2026-10-16"):
    return {"rcept_no": no, "rcept_dt": dt, "stock_code": code, "corp_name": name, "kind": kind, "payload": payload}


def test_kr_disclosures_week_scope_and_order():
    rows = [_disc("1", "111111", "소형사", "contract", {"amount": 5e9, "pct_of_revenue": 80.0, "title": "장비"}),
            _disc("2", "222222", "큰계약", "contract", {"amount": 9e10, "pct_of_revenue": 35.0, "title": "선박"}),
            _disc("3", "333333", "작은계약", "contract", {"amount": 1e9, "pct_of_revenue": 5.0, "title": "부품"}),
            _disc("4", "444444", "관심사", "contract", {"amount": 2e9, "pct_of_revenue": 3.0, "title": "용역"}),
            _disc("5", "222222", "큰계약", "prelim", {"period_end": "2026-09-30", "revenue": 5.04e12, "revenue_yoy_pct": 25.8,
                                                   "operating_income_yoy_pct": None, "operating_income_yoy_turn": "흑자전환"})]
    kd = g.kr_disclosures_week(rows, {"222222", "333333"}, {"444444": ["my"]})
    assert [x["symbol"] for x in kd["contract"]["items"]] == ["444444", "222222", "333333"]   # 유니버스 밖 소형사 제외
    assert kd["prelim"]["items"][0]["summary"] == "잠정실적 26.3Q 전년동기 대비 매출 +26% · 영업익 흑자전환"
    text = g.build_telegram_summary(_briefing(kr_disclosures=kd))
    assert "한국 공시</b> 지난 7일 공급계약 3 · 잠정실적 1" in text
    assert "관심사 공급계약 20억 (매출 대비 3.0%) · 용역 · 내 관심" in text
    assert text.index("관심사") < text.index("큰계약")
    assert "한국 공시" not in g.build_telegram_summary(_briefing())


def test_past_kr_notice_does_not_hide_next_date():
    # 10/14 잠정실적 예고는 지났다 - yfinance의 10/28(확정 실적)이 그 주에 남아야 한다
    rows = [{"ticker": "000660", "market": "KR", "earnings_date": "2026-10-28", "earnings_date_end": "2026-10-28", "is_estimate": 1}]
    merged = g.merge_kr_notices(rows, [{"ticker": "000660", "announce_date": "2026-10-14"}], "2026-10-26")
    assert [x["date"] for x in g.earnings_week_items(merged, "2026-10-26", {}, {})["items"]] == ["2026-10-28"]


def test_kr_disclosures_termination_and_amend():
    rows = [_disc("1", "222222", "해지사", "termination", {"amount": 2.9e11, "pct_of_revenue": 41.0, "reason": "상대방 사업 종료"}),
            _disc("2", "333333", "정정사", "amend", {"amount_changed": True, "amount_before": 8.58e9, "amount_after": 9.17e9,
                                                  "pct_before": 17.35, "pct_after": 18.53}),
            _disc("3", "333333", "날짜만", "amend", {"amount_changed": False, "reason": "계약기간 변경"})]
    kd = g.kr_disclosures_week(rows, {"222222", "333333"}, {})
    assert kd["termination"]["count"] == 1 and kd["amend"]["count"] == 1   # 날짜만 바뀐 정정은 뺀다
    text = g.build_telegram_summary(_briefing(kr_disclosures={**kd, "contract": {"count": 0, "items": []}, "prelim": {"count": 0, "items": []}}))
    assert "계약 해지 1 · 금액 정정 1" in text and "해지사 계약 해지 2,900억 (매출 대비 41.0%)" in text


def test_insider_week_grouping_and_telegram():
    rows = [{"market": "US", "symbol": "OXY", "owner": "Jackson", "role": "President and CEO · 이사", "trade_date": "2026-10-15",
             "filed_on": "2026-10-16", "value": 249_853, "plan": 0},
            {"market": "KR", "symbol": "043200", "owner": "(주)지본", "role": "10%이상주주", "trade_date": "2026-10-14",
             "filed_on": "2026-10-20", "value": 1.51e8, "plan": 0},
            {"market": "KR", "symbol": "043200", "owner": "(주)지본", "role": "10%이상주주", "trade_date": "2026-10-15",
             "filed_on": "2026-10-20", "value": 0.4e8, "plan": 0},
            {"market": "US", "symbol": "DVN", "owner": "A", "role": "CEO", "trade_date": "2026-10-14", "filed_on": "2026-10-15",
             "value": 100_000, "plan": 1},
            {"market": "US", "symbol": "DVN", "owner": "B", "role": "CFO", "trade_date": "2026-10-15", "filed_on": "2026-10-16",
             "value": 50_000, "plan": 1}]
    ins = g.insider_week_items(rows, {"KR:043200": ["theme"]}, {"KR:043200": "파루"},
                               {"US:OXY": {"status": "pass", "piotroski": 7, "reasons": []}})
    assert [x["symbol"] for x in ins["items"]] == ["043200"] and ins["tagged_count"] == 1
    assert ins["split_by_market"] == {"KR": {"tagged": 1, "discovery": 0}, "US": {"tagged": 0, "discovery": 2}}
    # 관심 밖: 계획 매수만 있는 DVN(2명)은 뒤로, OXY 먼저
    assert [x["symbol"] for x in ins["discovery"]] == ["OXY", "DVN"] and ins["discovery_count"] == 2
    kr = ins["items"][0]
    assert kr["buyers"] == 1 and kr["trades"] == 2 and kr["value"] == 1.91e8 and kr["last_date"] == "2026-10-15"
    assert ins["discovery"][1]["buyers"] == 2 and ins["discovery"][1]["all_plan"] and ins["discovery"][1]["finance"] is None
    text = g.build_telegram_summary(_briefing(insider_week=ins))
    assert "내부자 장내 매수</b> 지난 7일 🇺🇸 2 · 🇰🇷 1종목" in text
    assert "🇰🇷 파루 10%이상주주 1.9억 · 테마" in text and "🆕 관심 밖 2종목" in text
    assert "OXY President and CEO · 이사 $250K · 재무 통과" in text and "DVN 2명 $150K (계획 매수) · 재무 미확인" in text
    assert g.fmt_money(1.2e6, "US") == "$1.2M" and g.fmt_money(3e7, "KR") == "3,000만"


def test_us_8k_week_items_and_telegram():
    import json as _j

    def det(items, warn=False, earnings_only=False):
        return _j.dumps({"items": items, "warn": warn, "earnings_only": earnings_only})
    rows = [{"symbol": "AAA", "filed_on": "2026-10-16", "url": "u1",
             "detail": det([{"item": "1.01", "label": "중요 계약 체결", "warn": False, "excerpt": "On Oct..."}])},
            {"symbol": "BBB", "filed_on": "2026-10-14", "url": "u2",
             "detail": det([{"item": "5.02", "label": "임원·이사 변동(사임·퇴임)", "warn": True, "excerpt": "resign"}], warn=True)},
            {"symbol": "CCC", "filed_on": "2026-10-15", "url": "u3",
             "detail": det([{"item": "2.02", "label": "실적 발표", "warn": False, "excerpt": None}], earnings_only=True)},
            {"symbol": "DDD", "filed_on": "2026-10-13", "url": "u4",
             "detail": det([{"item": "2.02", "label": "실적 발표", "warn": False, "excerpt": None},
                            {"item": "5.02", "label": "임원·이사 변동(선임)", "warn": False, "excerpt": "appointed"}])}]
    u8 = g.us_8k_week_items(rows, {"US:DDD": ["my"]}, {})
    assert [x["symbol"] for x in u8["items"]] == ["DDD", "BBB", "AAA"]   # 관심 표시 → 주의 종류 → 최근 순, 실적만은 뺌
    assert u8["items"][0]["items"] == [{"item": "5.02", "label": "임원·이사 변동(선임)", "warn": False, "excerpt": "appointed"}]
    assert u8["by_kind"] == {"임원·이사 변동": 2, "중요 계약 체결": 1}
    text = g.build_telegram_summary(_briefing(us_8k_week=u8))
    assert "미국 주요 공시(8-K)</b> 지난 7일 3건 - 임원·이사 변동 2 · 중요 계약 체결 1" in text
    assert "BBB ⚠️임원·이사 변동(사임·퇴임)" in text and "DDD 임원·이사 변동(선임) · 내 관심" in text


def test_my_stocks_week_collects_from_sections():
    b = _briefing(
        earnings_week={"items": [{"market": "US", "symbol": "MU", "date": "2026-10-22", "estimate": False, "tags": ["my"]},
                                 {"market": "US", "symbol": "T", "date": "2026-10-21", "estimate": False, "tags": []}]},
        kr_disclosures={"contract": {"count": 1, "items": [{"symbol": "089790", "date": "2026-10-16", "summary": "공급계약 57억", "tags": ["note"]}]},
                        "termination": {"count": 1, "items": [{"symbol": "069260", "date": "2026-09-29", "summary": "계약 해지 2,939억", "tags": ["my"]}]},
                        "prelim": {"count": 0, "items": []}},
        us_8k_week={"items": [{"symbol": "MU", "date": "2026-10-16", "warn": False,
                               "items": [{"item": "5.02", "label": "임원·이사 변동(선임)", "warn": False}]}]},
        insider_week={"items": [], "discovery": [{"market": "KR", "symbol": "069260", "owners": ["A"], "roles": ["대표이사"],
                                                  "buyers": 1, "value": 3e8, "last_date": "2026-10-15"}]},
        turnaround={"added": [{"market": "US", "symbol": "MU", "basis": "1년", "yoy": 1.1}]},
        observation_reviews=[{"kind": "stock", "market": "KR", "ticker": "089790", "checkpoint": "4w"}])
    mine = {"US:MU": ["my"], "KR:089790": ["note"], "KR:069260": ["my"]}
    my = g.my_stocks_week(b, mine, {"KR:089790": "제이티", "KR:069260": "티케이지휴켐스"})
    assert [x["symbol"] for x in my["items"]] == ["MU", "069260", "089790"]   # 내 관심 → 생긴 일 수 → 종목
    mu = my["items"][0]
    assert [e["kind"] for e in mu["events"]] == ["실적 발표", "8-K", "실적 반전"] and mu["events"][2]["text"] == "새로 들어옴 (1년 +110%)"
    tk = my["items"][1]
    assert tk["events"][0]["warn"] and tk["events"][1]["text"] == "대표이사 3.0억"
    assert [e["kind"] for e in my["items"][2]["events"]] == ["한국 공시", "노트 회고"]
    text = g.build_telegram_summary(_briefing(my_stocks_week=my))
    assert text.index("관심 종목에 생긴 일</b> 3종목") < text.index("지난 1주")
    assert "🇰🇷 티케이지휴켐스 ⚠️한국 공시 계약 해지 2,939억 · 내부자 매수 대표이사 3.0억" in text
