from scripts.alert_data_health import message, problems


def test_problems_and_message():
    h = {"items": [
        {"key": "macro", "label": "매크로 지표", "status": "ok", "age_days": 0, "ok_days": 3, "cadence": "매일 아침"},
        {"key": "price_facts", "label": "차트 상태", "status": "late", "age_days": 5, "ok_days": 4, "cadence": "평일 밤"},
        {"key": "x", "label": "새 표", "status": "missing", "age_days": None, "ok_days": 9, "cadence": "매주"},
    ]}
    bad = problems(h)
    assert [b["key"] for b in bad] == ["price_facts", "x"]
    m = message(bad)
    assert "2개" in m and "[늦음] 차트 상태 - 마지막 5일 전" in m and "[없음] 새 표 - 마지막 기록 없음" in m
