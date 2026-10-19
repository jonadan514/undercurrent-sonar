"""기업 카드 FCF 수익률 (docs/SPEC_watchlist_growth.md 3장 "나중에 넣는다면 상세 카드에").

FCF 수익률 = 잉여현금흐름 / 시가총액. PER이 못 보는 것(설비투자가 큰 업종에서 이익이
현금으로 남는지)을 보여준다. company_growth.py와 같은 성격의 순수 함수 모듈 - 네트워크·DB
접근 없음, 이미 조회된 데이터만 받는다.

## 왜 3년 평균인가

FCF는 해마다 출렁인다 - 설비투자를 크게 한 해 한 번에 음수로 뒤집힌다(SPEC 3장이 이걸
이유로 미뤘다). 그래서 대표값은 **최근 3개 회계연도 FCF 평균 / 시가총액**으로 하고,
최근 1개 연도 값과 "3년 중 음수인 해 수"를 함께 낸다 - 평균이 양수여도 음수 해가 섞였는지
보이게.

## 등급을 만들지 않는다

밸류(PSR)처럼 3등분하거나 성장처럼 절대 기준 라벨을 붙이지 않는다. 표·필터에도 넣지
않고 상세 카드에 숫자로만 보여준다(SPEC 3장 결정, 원칙 1). 업종마다 정상 범위가 너무
달라(소프트웨어 vs 조선) 하나의 기준선이 거짓 라벨을 만든다.

## 데이터부족 (원칙 4)

  - 최근 3개 회계연도가 연속(연도 간격 정확히 2년)이 아니면 3년 평균은 None -
    company_growth._window와 같은 엄격함. 최근 연도 값은 1개 연도만 있어도 계산한다.
  - FCF 계정이 없으면 영업현금흐름 + 자본지출(yfinance는 자본지출을 음수로 준다)로 만든다.
    둘 중 하나라도 없으면 그 해는 FCF 없음.
  - 시가총액이 없거나 0 이하면 전부 None.
"""
from __future__ import annotations

FCF_KEYS = ("Free Cash Flow",)
OCF_KEYS = ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
CAPEX_KEYS = ("Capital Expenditure",)

YEARS = 3


def _pick(data: dict, keys: tuple[str, ...]) -> float | None:
    for k in keys:
        v = data.get(k)
        if v is not None:
            return float(v)
    return None


def annual_fcf(data: dict) -> float | None:
    """한 회계연도의 FCF. 직접 항목이 없으면 영업현금흐름 + 자본지출(음수)."""
    fcf = _pick(data, FCF_KEYS)
    if fcf is not None:
        return fcf
    ocf, capex = _pick(data, OCF_KEYS), _pick(data, CAPEX_KEYS)
    if ocf is None or capex is None:
        return None
    # 자본지출 부호가 양수로 들어오는 출처도 있다 - 빼는 방향으로 맞춘다.
    return ocf - abs(capex)


def fcf_yield(periods: list[tuple[str, dict]], market_cap: float | None) -> dict:
    """periods: 연차 현금흐름표 [(period_end: str, data: dict), ...] (정렬 무관).

    반환: {"yield_3y": float|None, "yield_latest": float|None,
           "negative_years": int|None, "latest_year": str|None}
    """
    empty = {"yield_3y": None, "yield_latest": None, "negative_years": None, "latest_year": None}
    if market_cap is None or market_cap <= 0 or not periods:
        return empty

    ordered = sorted(periods, key=lambda p: p[0], reverse=True)
    values = [(p[0], annual_fcf(p[1])) for p in ordered]
    values = [(d, v) for d, v in values if v is not None]
    if not values:
        return empty

    out = dict(empty)
    out["latest_year"] = values[0][0][:4]
    out["yield_latest"] = values[0][1] / market_cap

    window = values[:YEARS]
    if len(window) == YEARS:
        try:
            years = [int(d[:4]) for d, _ in window]
        except (ValueError, TypeError):
            years = []
        if years and years[0] - years[-1] == YEARS - 1:
            fcfs = [v for _, v in window]
            out["yield_3y"] = sum(fcfs) / YEARS / market_cap
            out["negative_years"] = sum(1 for v in fcfs if v < 0)
    return out
