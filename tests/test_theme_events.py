from datetime import date

from src.analyzers.theme_events import busier, by_theme, insider_events, kr_event, us8k_event, week_index, weekly

TODAY = date(2026, 10, 21)


def test_kr_event_kinds():
    base = {"rcept_no": "1", "rcept_dt": "2026-10-16", "stock_code": "089790", "corp_name": "제이티"}
    e = kr_event({**base, "kind": "contract", "payload": {}}, "공급계약 57억")
    assert e["kind"] == "공급계약" and e["text"] == "57억" and not e["warn"] and e["url"].endswith("rcpNo=1")
    assert kr_event({**base, "kind": "termination", "payload": {}}, "x")["warn"]
    assert kr_event({**base, "kind": "amend", "payload": {"amount_changed": False}}, "x") is None
    assert kr_event({**base, "kind": "notice", "payload": {}}, "x") is None


def test_us8k_event_skips_earnings():
    row = {"symbol": "TSLA", "filed_on": "2026-10-15", "url": "u"}
    assert us8k_event(row, {"earnings_only": True, "items": [{"item": "2.02", "label": "실적 발표", "warn": False}]}) is None
    e = us8k_event(row, {"items": [{"item": "2.02", "label": "실적 발표", "warn": False},
                                   {"item": "1.02", "label": "중요 계약 해지", "warn": True, "excerpt": "Termination"}]})
    assert e["text"] == "중요 계약 해지" and e["warn"] and e["excerpt"] == "Termination"


def test_insider_grouped_by_owner():
    rows = [{"market": "KR", "symbol": "043200", "owner": "지본", "role": "10% 이상 주주", "filed_on": "2026-10-14", "value": 1e8, "plan": 0},
            {"market": "KR", "symbol": "043200", "owner": "지본", "role": "10% 이상 주주", "filed_on": "2026-10-20", "value": 5e7, "plan": 0}]
    ev = insider_events(rows)
    assert len(ev) == 1 and ev[0]["value"] == 1.5e8 and ev[0]["date"] == "2026-10-20" and "2건" in ev[0]["text"]


def test_by_theme_counts_and_window():
    events = [{"date": "2026-10-19", "ticker": "A", "type": "disclosure", "warn": False},
              {"date": "2026-10-01", "ticker": "B", "type": "disclosure", "warn": True},
              {"date": "2026-10-18", "ticker": "B", "type": "insider", "warn": False},
              {"date": "2026-08-01", "ticker": "A", "type": "disclosure", "warn": False},   # 30일 밖
              {"date": "2026-10-19", "ticker": "Z", "type": "disclosure", "warn": False}]  # 소속 아님
    r = by_theme({"ship": ["A", "B", "C"], "none": ["C"]}, events, TODAY)
    c = r["ship"]["counts"]
    assert {k: c[k] for k in ("disclosure_7d", "disclosure_30d", "warn_30d", "insider_cos_7d", "insider_cos_30d", "companies_30d", "members")} \
        == {"disclosure_7d": 1, "disclosure_30d": 2, "warn_30d": 1, "insider_cos_7d": 1, "insider_cos_30d": 1, "companies_30d": 2, "members": 3}
    assert c["weekly"]["disclosure"]["weeks"] == [1, 0, 1, 0, 0]   # 10/19 이번 주, 10/01 = 20일 전 → 2주 전(칸 2)
    assert [e["date"] for e in r["ship"]["items"]] == ["2026-10-19", "2026-10-18", "2026-10-01"]
    assert r["none"]["counts"]["companies_30d"] == 0 and r["none"]["items"] == []


def test_week_index_buckets():
    assert week_index("2026-10-21", TODAY) == 0 and week_index("2026-10-15", TODAY) == 0
    assert week_index("2026-10-14", TODAY) == 1 and week_index("2026-09-17", TODAY) == 4
    assert week_index("2026-09-16", TODAY) is None


def test_weekly_counts_coverage_and_busier():
    marks = [("A", "2026-10-20"), ("A", "2026-10-19"), ("B", "2026-10-18"), ("C", "2026-10-16"),   # 이번 주 4건
             ("A", "2026-10-10"), ("B", "2026-10-02"), ("C", "2026-09-25")]                      # 1·2·3주 전 1건씩
    w = weekly(marks, TODAY, None, distinct=False)
    assert w["weeks"] == [4, 1, 1, 1, 0] and w["base_weeks"] == 4 and w["avg"] == 0.75
    assert busier(w, "disclosure")                      # 4 >= 3 이고 4 >= 2 x 0.75
    # 데이터가 10/01부터면 3·4주 전(9/24~9/30, 9/17~9/23)은 '데이터 없음' - 0으로 치지 않는다
    w2 = weekly(marks, TODAY, "2026-10-01", distinct=False)
    assert w2["weeks"] == [4, 1, 1, None, None] and w2["base_weeks"] == 2 and w2["avg"] == 1.0
    # 직전 주가 하나뿐이면 비교 기준 부족
    w3 = weekly(marks, TODAY, "2026-10-08", distinct=False)
    assert w3["weeks"][2:] == [None, None, None] and w3["avg"] is None and not busier(w3, "disclosure")
    # 내부자: 같은 종목 여러 줄은 한 회사
    wi = weekly([("A", "2026-10-20"), ("A", "2026-10-19"), ("B", "2026-10-18")], TODAY, None, distinct=True)
    assert wi["weeks"] == [2, 0, 0, 0, 0] and busier(wi, "insider")
    # 평소에도 많은 테마는 '평소보다 많음'이 아니다
    assert not busier({"weeks": [6, 4, 5, 3, 4], "avg": 4.0}, "disclosure")
