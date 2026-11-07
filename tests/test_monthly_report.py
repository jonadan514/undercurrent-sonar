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
         "watchlist": {"watchlist": {"added_count": 3, "removed_count": 0}}, "reviews": []}
    facts = mr.summary_facts(r)
    assert "미국 시장 환경 흐름: 긴축 압력(첫 주만) → 위험 회피(마지막 주)" in facts
    assert not any(re.search(r"\d+\s*(%|개|종목)", f) for f in facts)


def test_regime_flow_and_ordinal():
    assert mr.regime_flow(["긴축 압력", "위험 회피", "위험 회피", "위험 회피"]) == "긴축 압력(첫 주만) → 위험 회피(이후 계속)"
    assert mr.regime_flow(["", "", ""]) == "뚜렷한 조합 없음(한 달 내내)"
    assert mr.regime_flow([]) == ""
    assert mr.ordinal_week(["2026-10-05", "2026-10-12"], "2026-10-12") == "둘째 주"
