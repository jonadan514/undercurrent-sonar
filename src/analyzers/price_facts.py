"""차트 상태 사실(2026-11-15, 사용자: 종목을 밸류·실적·차트로 본다 - 차트만 툴 밖에서 봐야 했다).

판정·점수 없이 사실만(원칙 1): 52주 범위 안 위치, 200일 이동평균 위/아래와 그 기울기, 1·3개월 수익률, 52주 고점 대비.
값은 거래일 종가(수정주가) 목록에서만 나온다. 계산할 만큼 기록이 없으면 None(데이터 부족, 원칙 4).
"""
from __future__ import annotations

from datetime import date

WEEKS_52 = 252        # 거래일
MA_LONG = 200
SLOPE_LAG = 20        # 200일선 기울기: 지금 vs 20거래일 전
RET_1M, RET_3M = 21, 63
MIN_BARS = RET_3M + 1


def completed(series: list[tuple[str, float]], today: date) -> list[tuple[str, float]]:
    """오늘 막대 제외 - 장중이면 종가가 아니다(signal_check.completed_bars와 같은 이유)."""
    t = today.isoformat()
    return [x for x in series if x[0] < t and x[1] is not None and x[1] > 0]


def price_facts(series: list[tuple[str, float]]) -> dict | None:
    """(날짜, 종가) 날짜순 목록 -> 차트 사실. 3개월치(64거래일)도 없으면 None."""
    if len(series) < MIN_BARS:
        return None
    closes = [c for _, c in series]
    last = closes[-1]
    win = closes[-WEEKS_52:]
    hi, lo = max(win), min(win)
    out: dict = {
        "as_of": series[-1][0],
        "close": last,
        "high_52w": hi,
        "low_52w": lo,
        # 52주(기록이 짧으면 있는 만큼) 범위 안에서 지금 위치 0~1. 범위가 0이면 None
        "pos_52w": (last - lo) / (hi - lo) if hi > lo else None,
        "from_high": last / hi - 1,
        "range_days": len(win),
        "ret_1m": last / closes[-1 - RET_1M] - 1,
        "ret_3m": last / closes[-1 - RET_3M] - 1,
        "ma200": None, "above_ma200": None, "ma200_slope": None,
    }
    if len(closes) >= MA_LONG:
        ma = sum(closes[-MA_LONG:]) / MA_LONG
        out["ma200"] = ma
        out["above_ma200"] = 1 if last > ma else 0
        if len(closes) >= MA_LONG + SLOPE_LAG:
            prev = sum(closes[-MA_LONG - SLOPE_LAG:-SLOPE_LAG]) / MA_LONG
            out["ma200_slope"] = ma / prev - 1
    return out
