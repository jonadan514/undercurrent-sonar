"""시장 환경(레짐) 축 - 2026-11-05, 마스터 플랜 2단계 '레짐 모듈'(사용자 결정: 축별 표시 + 정해진 조합에만 이름).

예전 '시장 체제 판정'(2026-08 삭제)은 지표를 가중합해 공격/중립/방어 등급 하나를 매겼다 - 원칙 1 위반. 여기서는 테마 레이더와 같은 방식:
축마다 따로(수준·방향) 보여 주고, 정해진 조합에만 이름을 붙인다. 매수·매도·비중 같은 행동 지시는 없다.

  수준  그 지표 자신의 지난 1년(최대 LOOKBACK 거래일) 안에서 상위 LEVEL_PCT 이상이면 '높은 편', 하위면 '낮은 편', 그 사이 '보통'
  방향  최근 WINDOW 거래일 변화 ÷ 지난 1년 동안의 WINDOW일 변화의 표준편차 - Z 이상이면 ↑, -Z 이하면 ↓, 그 사이 →
        (지표마다 단위가 달라도 '평소 4주 변화폭에 비해 큰가'로 같은 잣대가 된다)
  외국인 순매수는 수준 대신 20거래일 합의 부호(순매수/순매도)와, 20일 합이 평소 20일 합에 비해 큰지로 방향을 본다.
표본이 MIN_OBS보다 적으면 '데이터 부족'(원칙 4 - 계산 불가는 판정이 아니다). 숫자는 저장된 값 그대로, GPT 없음.
"""
from __future__ import annotations

import statistics

LOOKBACK = 252     # 1년 거래일
WINDOW = 20        # 4주
LEVEL_PCT = 0.20   # 상·하위 20%
Z = 1.0            # 평소 4주 변화폭(표준편차)의 1배
MIN_OBS = 120      # 반년치보다 적으면 수준·방향을 내지 않는다

# 축 = 대표 지표 하나. 곁들여 보여 줄 지표(context)는 판정에 안 쓴다.
AXES = {
    "US": [("rates", "금리", "us10y"), ("credit", "신용", "hy_spread"), ("dollar", "달러", "dxy"), ("vol", "변동성", "vix")],
    "KR": [("rates", "금리", "kr3y"), ("credit", "신용", "hy_spread"), ("fx", "환율", "usdkrw"), ("vol", "변동성", "vix"),
           ("flows", "외국인 수급", "kospi_foreign")],
}
CONTEXT = {"US": ["spread_10y_2y", "real10y", "wti", "copper"], "KR": ["kr10y", "wti"]}
LABEL_KO = {"us10y": "미 10년물", "hy_spread": "미 하이일드 스프레드", "dxy": "달러인덱스", "vix": "VIX", "kr3y": "국고채 3년",
            "kr10y": "국고채 10년", "usdkrw": "원/달러", "kospi_foreign": "코스피 외국인 순매수(20일 합)",
            "spread_10y_2y": "10년-2년 금리차", "real10y": "미 10년 실질금리", "wti": "WTI", "copper": "구리"}

# 조합 이름 - 테마 라벨처럼 정해진 조합에만. 여러 개가 함께 맞을 수 있다(예: 긴축 압력 + 위험 회피).
# 조건: 축 -> 방향 집합(up/flat/down). 축이 데이터 부족이면 그 조합은 판정하지 않는다.
COMBOS = {
    "US": [
        ("risk_off", "위험 회피", "변동성과 신용 스프레드가 함께 오르고 달러도 약해지지 않음",
         {"vol": {"up"}, "credit": {"up"}, "dollar": {"up", "flat"}}),
        ("risk_on", "위험 선호", "변동성과 신용 스프레드가 함께 내림", {"vol": {"down"}, "credit": {"down"}}),
        ("tightening", "긴축 압력", "금리와 달러가 함께 오름", {"rates": {"up"}, "dollar": {"up"}}),
        ("easing", "완화 기대", "금리가 내리고 신용 스프레드는 오르지 않음", {"rates": {"down"}, "credit": {"down", "flat"}}),
    ],
    "KR": [
        ("risk_off", "위험 회피", "변동성과 신용 스프레드가 함께 오르고 원화도 강해지지 않음",
         {"vol": {"up"}, "credit": {"up"}, "fx": {"up", "flat"}}),
        ("risk_on", "위험 선호", "변동성과 신용 스프레드가 함께 내림", {"vol": {"down"}, "credit": {"down"}}),
        ("krw_pressure", "원화 약세 압력", "원/달러가 오르고 외국인이 평소보다 크게 순매도", {"fx": {"up"}, "flows": {"down"}}),
        ("easing", "완화 기대", "국고채 금리가 내리고 신용 스프레드는 오르지 않음", {"rates": {"down"}, "credit": {"down", "flat"}}),
    ],
}
ARROW = {"up": "↑", "flat": "→", "down": "↓", None: "-"}
LEVEL_KO = {"high": "높은 편", "mid": "보통", "low": "낮은 편", None: "데이터 부족"}


DEDUPE_KEYS = {"kr3y", "kr10y"}   # 국고채(pykrx)는 휴장일에 직전 값이 그대로 들어온 행이 섞인다 - 하이일드 스프레드처럼 같은 값이
                                  # 이어지는 게 정상인 지표에는 쓰지 않는다(4주 = 20개 관측이 늘어나 버림)


def _dedupe(points: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """날짜순 정렬 + 휴장일에 직전 값이 그대로 들어온 연속 중복 제거(브리핑 get_kr_rate_week와 같은 처리)."""
    pts = sorted((d, float(v)) for d, v in points if v is not None)
    out: list[tuple[str, float]] = []
    for d, v in pts:
        if out and out[-1][0] == d:
            out[-1] = (d, v)
        elif not out or v != out[-1][1]:
            out.append((d, v))
    return out


def indicator_state(points: list[tuple[str, float]], as_of: str, *, cumulative: bool = False, dedupe: bool = False) -> dict:
    """한 지표의 as_of 시점 상태. points: [(날짜, 값)]. cumulative=True면 일별 값(순매수)을 WINDOW일 합으로 바꿔 본다.
    반환 {value, chg, level, dir, z, n} - 표본 부족이면 level·dir None."""
    clean = _dedupe(points) if dedupe else sorted((d, float(v)) for d, v in points if v is not None)
    pts = [(d, v) for d, v in clean if d <= as_of]
    vals = [v for _, v in pts][-(LOOKBACK + WINDOW):]
    if cumulative:
        vals = [sum(vals[i - WINDOW + 1:i + 1]) for i in range(WINDOW - 1, len(vals))]
    if not vals:
        return {"value": None, "chg": None, "level": None, "dir": None, "z": None, "n": 0, "as_of": None}
    cur = vals[-1]
    base = {"value": cur, "n": len(vals), "as_of": pts[-1][0]}
    if len(vals) < MIN_OBS:
        return {**base, "chg": None, "level": None, "dir": None, "z": None}
    window = vals[-LOOKBACK:]
    if cumulative:   # 순매수 합은 수준 대신 부호
        level = "high" if cur > 0 else "low" if cur < 0 else "mid"
        chg = cur
        changes = window
    else:
        rank = sum(1 for v in window if v < cur) / len(window)
        level = "high" if rank >= 1 - LEVEL_PCT else "low" if rank <= LEVEL_PCT else "mid"
        chg = cur - vals[-1 - WINDOW]
        changes = [vals[i] - vals[i - WINDOW] for i in range(len(vals) - len(window), len(vals)) if i - WINDOW >= 0]
    sd = statistics.pstdev(changes) if len(changes) >= 2 else 0
    if cumulative:   # 20일 합이 평소 20일 합의 평균에서 얼마나 떨어졌나
        mu = statistics.fmean(changes)
        z = (cur - mu) / sd if sd else 0.0
    else:
        z = chg / sd if sd else 0.0
    d = "up" if z >= Z else "down" if z <= -Z else "flat"
    return {**base, "chg": chg, "level": level, "dir": d, "z": round(z, 2)}


def market_state(series: dict[str, list[tuple[str, float]]], market: str, as_of: str) -> dict:
    """시장 하나의 as_of 시점 축 상태 + 맞는 조합 이름들."""
    axes = {}
    for axis, name, key in AXES[market]:
        st = indicator_state(series.get(key) or [], as_of, cumulative=(key == "kospi_foreign"), dedupe=key in DEDUPE_KEYS)
        axes[axis] = {"name": name, "key": key, "label": LABEL_KO.get(key, key), **st}
    combos = []
    for cid, cname, mean, cond in COMBOS[market]:
        if all(axes.get(a, {}).get("dir") in allowed for a, allowed in cond.items()):
            combos.append({"id": cid, "name": cname, "meaning": mean})
    context = {k: indicator_state(series.get(k) or [], as_of, dedupe=k in DEDUPE_KEYS) for k in CONTEXT[market]}
    return {"market": market, "as_of": as_of, "axes": axes, "combos": combos, "context": context}
