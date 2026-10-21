from datetime import date

from src.analyzers.signal_check import (distribution, fwd_return, insider_signals, median_return, theme_signals,
                                        turnaround_signals, week_window)


def test_week_window_is_the_seven_days_before_monday():
    assert week_window("2026-10-26") == ("2026-10-19", "2026-10-25")


def test_insider_signals_grouped_and_watched_flag():
    rows = [{"market": "US", "symbol": "CNX", "owner": "A", "value": 1e5, "plan": 0},
            {"market": "US", "symbol": "CNX", "owner": "B", "value": 2e5, "plan": 0},
            {"market": "US", "symbol": "CNX", "owner": "A", "value": None, "plan": 0},
            {"market": "KR", "symbol": "043200", "owner": "지본", "value": 1e8, "plan": 0}]
    sig = {s["symbol"]: s for s in insider_signals(rows, {"KR:043200"})}
    assert sig["CNX"]["detail"] == {"watched": False, "value": 3e5, "trades": 3, "all_plan": False, "buyers": 2}
    assert sig["043200"]["detail"]["watched"] and sig["043200"]["kind"] == "insider_buy"


def test_turnaround_needs_previous_snapshot():
    cur = [{"market": "US", "symbol": "MU", "basis": "1년", "yoy": 1.1}, {"market": "KR", "symbol": "005930", "basis": "1년", "yoy": 0.5}]
    assert turnaround_signals(cur, None) == []   # 비교할 직전 주가 없으면 '새로'로 치지 않는다
    new = turnaround_signals(cur, [{"market": "KR", "symbol": "005930"}])
    assert [(s["symbol"], s["detail"]["basis"]) for s in new] == [("MU", "1년")]


def test_theme_signals_only_busier_with_members():
    wk = {"disclosure": {"weeks": [6, 2, 1, 3, 2]}, "insider": {"weeks": [0, 0, 0, 0, 0]}}
    result = {"power_grid": {"counts": {"busier": {"disclosure": True, "insider": False}, "weekly": wk}},
              "infra": {"counts": {"busier": {"disclosure": False, "insider": False}, "weekly": wk}}}
    sig = theme_signals("KR", result, {"power_grid": ["B", "A", "A"]}, {"power_grid": True})
    assert len(sig) == 1 and sig[0]["symbol"] == "power_grid"
    assert sig[0]["detail"]["members"] == ["A", "B"] and sig[0]["detail"]["busier"] == ["disclosure"] and sig[0]["detail"]["quiet_axes"]


def test_fwd_return_waits_for_horizon_and_uses_next_trading_day():
    s = [("2026-09-01", 100.0), ("2026-09-03", 102.0), ("2026-09-29", 110.0), ("2026-10-01", 111.0)]
    # 9/2(휴장) 신호 -> 9/3 시작 102, 28일 뒤 9/30 -> 10/1 111
    assert abs(fwd_return(s, "2026-09-02", 28, date(2026, 10, 21)) - (111 / 102 - 1)) < 1e-9
    assert fwd_return(s, "2026-09-02", 28, date(2026, 9, 29)) is None   # 아직 기간이 안 지남
    assert fwd_return(s, "2026-09-02", 84, date(2026, 12, 31)) is None  # 끝 날짜 가격 없음


def test_median_return_and_distribution():
    assert median_return([0.1, None, 0.3]) == (None, 2)          # 3개 미만이면 데이터부족
    assert median_return([0.1, -0.2, 0.3, None]) == (0.1, 3)
    d = distribution([0.1, -0.1, 0.0, 0.2, 0.3])
    assert d["n"] == 5 and d["median"] == 0.1 and d["q1"] == 0.0 and d["q3"] == 0.2
    assert distribution([]) == {"n": 0, "median": None, "q1": None, "q3": None}
