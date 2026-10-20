from datetime import date

from src.analyzers.theme_events import by_theme, insider_events, kr_event, us8k_event

TODAY = date(2026, 10, 21)


def test_kr_event_kinds():
    base = {"rcept_no": "1", "rcept_dt": "2026-10-16", "stock_code": "089790", "corp_name": "제이티"}
    e = kr_event({**base, "kind": "contract", "payload": {}}, "공급계약 57억")
    assert e["kind"] == "공급계약" and not e["warn"] and e["url"].endswith("rcpNo=1")
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
    assert c == {"disclosure_7d": 1, "disclosure_30d": 2, "warn_30d": 1, "insider_cos_7d": 1, "insider_cos_30d": 1,
                 "companies_30d": 2, "members": 3}
    assert [e["date"] for e in r["ship"]["items"]] == ["2026-10-19", "2026-10-18", "2026-10-01"]
    assert r["none"]["counts"]["companies_30d"] == 0 and r["none"]["items"] == []
