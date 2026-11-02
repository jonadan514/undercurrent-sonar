"""Phase A-4: 실적 축(매출 성장률) 계산.

SPEC: docs/radar/SPEC_phase_a_signals.md §3

SPEC 원안은 "가속도"(g_t > g_t-1, 6분기 필요)를 계산하지만, 실제 백필해보니
yfinance 무료 분기 재무제표(quarterly_financials/quarterly_income_stmt 둘 다)가
사실상 5분기까지만 준다(2026-09-01 확인 - AAPL 등 다수 종목이 정확히 5분기,
그 이상 있는 종목도 오래된 분기는 Total Revenue 자체가 비어있음). 6분기가
필요한 "가속도" 공식은 구조적으로 계산이 안 되어 전체 종목이 데이터부족으로
나오는 문제를 실제로 겪음.

사용자 결정(2026-09-01): 5분기로 계산 가능한 "전년동기 대비 성장" 하나만
본다 - "가속" 개념은 포기하되, 계절성 보정(전년동기 비교)은 유지. 이 도구가
심화분석 이전의 1차 스크리닝 용도라 이 정도 단순화로 충분하다는 판단.

2026-09-07 개정 - 절대 기준("성장률 > 0")에서 상대 기준("같은 시장 중앙값
초과")으로 바꿈. 이유: 성장률 > 0은 미국 138개 기업 중 92%, 한국 58개 중
90%가 통과해서 아무도 못 걸렀고, 그 결과 실적 축이 판정 가능한 테마 전부
up2로 나와 **정보를 전혀 주지 않는 상수**가 돼 있었다(미국 14/14, 한국 7/8).
라벨도 사실상 뉴스·주가로만 결정되고 있었다.

상대 기준의 좋은 성질: 기업의 절반이 자동으로 기준선 위에 놓이므로 테마별
비율이 0.50 중심으로 분포한다 - 기존 임계값(up2 0.70 / up1 0.55 / down 0.45)이
0.50 대칭이라 임계값을 안 바꿔도 그대로 의미를 갖는다. 시장 사이클(호황이면
전부 up, 불황이면 전부 down)에도 흔들리지 않는다. 주가 축이 이미 "지수 대비
초과수익"이라는 상대 비교를 쓰고 있어 도구 전체와도 일관된다.

트레이드오프: "실적이 좋아졌다"가 아니라 "같은 시장 기업들보다 잘했다"는
뜻이 된다. 시장 전체가 역성장하는 국면에서도 상위 테마는 up으로 나올 수 있다.
"""
from __future__ import annotations

import statistics

import pandas as pd

# 5개 분기 필요 - g_yoy(t/t-4) 계산에 t-4까지 있어야 함 (인덱스 0~4).
# yfinance 무료 API가 실질적으로 제공하는 상한이 5분기라 이 이상 요구할 수 없음.
MIN_QUARTERS = 5

# 시장 중앙값을 신뢰하려면 최소 이만큼의 기업 표본이 필요하다. 미달이면
# 중앙값 대신 절대 기준 0으로 폴백한다(개정 전 동작).
MIN_MEDIAN_SAMPLE = 20


def _quarter_label(ts) -> str:
    q = (ts.month - 1) // 3 + 1
    return f"{ts.year}-Q{q}"


def yoy_growth(quarterly_revenue: pd.Series | None) -> float | None:
    """전년동기 대비 매출 성장률(g_yoy = 이번 분기 / 작년 같은 분기 - 1).
    계산 불가면 None(분기 부족·분모 0) - 탈락이 아니라 데이터부족이다."""
    if quarterly_revenue is None or len(quarterly_revenue) < MIN_QUARTERS:
        return None
    denom = quarterly_revenue.iloc[4]
    if not denom:
        return None
    return quarterly_revenue.iloc[0] / denom - 1


def market_median_growth(quarterly_revenue_by_ticker: dict[str, pd.Series | None],
                          min_sample: int = MIN_MEDIAN_SAMPLE) -> float | None:
    """이 시장 기업들의 YoY 성장률 중앙값. 표본이 min_sample 미만이면 None
    (중앙값을 신뢰할 수 없어 절대 기준 0으로 폴백하기 위함)."""
    vals = [g for g in (yoy_growth(r) for r in quarterly_revenue_by_ticker.values())
            if g is not None]
    if len(vals) < min_sample:
        return None
    return statistics.median(vals)


def reference_growth_for_market(universe_revenue: dict[str, pd.Series | None], market: str,
                                 min_sample: int = MIN_MEDIAN_SAMPLE) -> float | None:
    """한 시장의 기준 성장률 = 그 시장 **유니버스 전체**의 YoY 성장률 중앙값.

    테마 소속 기업만 표본으로 쓰면 안 된다(2026-09-21 수정). 소속 기업이 곧 표본이면 절반이
    자동으로 기준 위에 놓여 개선 비율이 0.5 근처로 쏠리고, 테마가 몰린 업종의 성장이 기준선에
    그대로 섞인다. 미국은 S&P500, 한국은 스크리닝 유니버스 전체를 넘겨받는다.

    market은 로그·확장을 위한 이름표일 뿐 계산에는 쓰지 않는다 - 미국과 한국을 한 덩어리로
    섞지 않는 것은 호출부가 시장별로 따로 넘기는 것으로 보장한다.
    """
    return market_median_growth(universe_revenue, min_sample)


def classify_company_earnings(quarterly_revenue: pd.Series | None,
                               reference_growth: float = 0.0) -> tuple[str, str | None]:
    """분기별 매출 Series(index=기간, 최신이 0번째, NaN 제거됨)를 받아
    (status, quarter_label)을 반환한다. status는 'improved'|'not_improved'|'insufficient'.

    성장률이 reference_growth를 넘으면 improved. reference_growth는 보통 같은
    시장의 중앙값이며, 0을 주면 예전(절대 기준) 동작과 같다.
    """
    g_yoy = yoy_growth(quarterly_revenue)
    if g_yoy is None:
        return "insufficient", None

    status = "improved" if g_yoy > reference_growth else "not_improved"
    return status, _quarter_label(quarterly_revenue.index[0])


def compute_earn_signal(members: list[dict], quarterly_revenue_by_ticker: dict[str, pd.Series | None],
                         thresholds: dict, reference_growth: float | None = None) -> dict:
    """members: linkage 필터링이 이미 적용된 theme_members 행 목록(딕셔너리,
    최소 'ticker' 키 필요).
    reference_growth: 이 시장의 기준 성장률(보통 중앙값). None이면 0(절대 기준).
    반환: {members, improved, insufficient, ratio, arrow, as_of, reference_growth}."""
    ref = 0.0 if reference_growth is None else reference_growth
    improved = 0
    insufficient = 0
    quarter_labels: list[str] = []

    for m in members:
        revenue = quarterly_revenue_by_ticker.get(m["ticker"])
        status, q_label = classify_company_earnings(revenue, ref)
        if status == "insufficient":
            insufficient += 1
            continue
        if status == "improved":
            improved += 1
        if q_label:
            quarter_labels.append(q_label)

    total = len(members)
    valid = total - insufficient
    as_of = max(quarter_labels) if quarter_labels else None

    # SPEC §3.3 - 표본 부족(5명 미만) 또는 데이터 신뢰 불가(insufficient 40% 초과)면 na
    if valid < 5 or (total and insufficient / total > 0.4):
        return {"members": total, "improved": improved, "insufficient": insufficient,
                "ratio": None, "arrow": "na", "as_of": as_of, "reference_growth": ref}

    ratio = improved / valid
    if ratio >= thresholds.get("strong_up", 0.70):
        arrow = "up2"
    elif ratio >= thresholds.get("up", 0.55):
        arrow = "up1"
    elif ratio <= thresholds.get("down", 0.45):
        arrow = "down"
    else:
        arrow = "flat"

    return {"members": total, "improved": improved, "insufficient": insufficient,
            "ratio": ratio, "arrow": arrow, "as_of": as_of, "reference_growth": ref}


# ── 잠정실적 미리보기 (2026-11-02, 사용자 결정: 실적 시즌 활용 1번) ──────────────
# 실적 축은 분기 재무가 캐시에 들어와야 움직여서 한국은 분기보고서(분기 끝 45일 뒤) 무렵까지 늦다. 그 사이 한국 회사가 내는
# 잠정실적 공시(DART 원문 표에서 파싱한 매출·전년동기 대비 %)로 같은 질문 - "시장보다 매출이 더 자랐나" - 을 미리 본다.
# 세 축 화살표·라벨에는 넣지 않는다: 숫자의 출처가 재무 캐시가 아니고(원칙 2의 '숫자는 fundamentals_cache에서만'),
# 잠정 값은 나중에 바뀔 수 있으며, 공시를 낸 회사만의 값이라 분기가 섞인다. 화면에는 '잠정'으로 따로 보인다.

def prelim_quarter_end(today) -> str:
    """지금 잠정실적이 나오는 분기 = 오늘 직전에 끝난 분기 말일('2026-09-30')."""
    q_end_month = ((today.month - 1) // 3) * 3          # 이번 분기 시작 전 달(0이면 작년 12월)
    if q_end_month == 0:
        return f"{today.year - 1}-12-31"
    last_day = {3: 31, 6: 30, 9: 30}[q_end_month]
    return f"{today.year}-{q_end_month:02d}-{last_day}"


def prelim_rev_yoy(payload: dict) -> float | None:
    """잠정실적 payload -> 매출 전년동기 대비(소수). 회사가 적은 증감률이 두 금액과 맞을 때만(수집기가 확인한 revenue_yoy_pct)
    - 월·연간 실적, 확인 안 된 값은 None(데이터부족)."""
    if payload.get("monthly") or payload.get("annual"):
        return None
    pct = payload.get("revenue_yoy_pct")
    try:
        return None if pct is None else float(pct) / 100
    except (TypeError, ValueError):
        return None


def latest_prelims(rows: list[dict], quarter_end: str) -> dict[str, float]:
    """kr_disclosures 잠정실적 줄(stock_code, rcept_no, payload) -> {종목: 매출 YoY}. 그 분기 것만, 정정이 있으면 가장 늦은 공시."""
    best: dict[str, tuple[str, float | None]] = {}
    for r in rows:
        p = r["payload"]
        if p.get("period_end") != quarter_end:
            continue
        code, no = r["stock_code"], str(r["rcept_no"])
        if code not in best or no > best[code][0]:
            best[code] = (no, prelim_rev_yoy(p))
    return {code: g for code, (_, g) in best.items() if g is not None}


def prelim_market_median(prelims: dict[str, float], min_sample: int = MIN_MEDIAN_SAMPLE) -> float | None:
    """잠정실적을 낸 그 시장 회사들의 매출 YoY 중앙값. 표본이 적으면 None - 비교하지 않고 건수만 보인다."""
    vals = list(prelims.values())
    return statistics.median(vals) if len(vals) >= min_sample else None


def compute_prelim_preview(members: list[dict], prelims: dict[str, float], median: float | None, quarter_end: str) -> dict:
    """테마 소속 기업 중 잠정실적을 낸 곳과, 그중 매출 YoY가 시장 잠정 중앙값을 넘은 곳. 비율·화살표는 만들지 않는다(원칙 1)."""
    vals = [prelims[m["ticker"]] for m in members if m["ticker"] in prelims]
    q = (int(quarter_end[5:7]) - 1) // 3 + 1
    return {"quarter": f"{quarter_end[:4]}-Q{q}", "n": len(vals),
            "beat": None if median is None else sum(1 for g in vals if g > median), "median": median}


# ── 한국 분기 매출 출처: DART 먼저 (2026-11-02, 사용자 결정 1번) ─────────────────
# 실적 축은 재무 캐시의 yfinance 분기 매출을 썼는데, yfinance는 한국 분기 실적을 늦고 들쭉날쭉하게 올려 분기보고서가 나온 뒤에도
# 지난 분기에 머물 수 있었다. 토요일 DART 수집(quarterly_financials_raw, 공시 원본 - 연결 우선)이 테마 소속까지 받게 되어,
# 한국은 둘 중 최신 분기가 더 늦은 쪽을 쓰고 같으면 DART를 쓴다. LLM이 만든 숫자는 어디에도 없다(원칙 2의 취지).

def dart_revenue_series(quarters: list[dict]) -> pd.Series | None:
    """select_quarters 결과(최신 분기부터) -> yoy_growth가 읽는 분기 매출 Series(최신이 0번째, 인덱스 = 분기 말일).
    중간에 빠진 분기·매출 없는 분기에서 멈춘다 - iloc[4]가 '작년 같은 분기'여야 해서."""
    vals, idx = [], []
    prev = None
    for r in quarters:
        key = (int(r["fiscal_year"]), int(r["fiscal_quarter"]))
        if prev is not None:
            y, q = prev
            if key != ((y, q - 1) if q > 1 else (y - 1, 4)):
                break
        if r.get("revenue") is None:
            break
        vals.append(float(r["revenue"]))
        idx.append(pd.Period(f"{key[0]}Q{key[1]}", freq="Q").end_time.normalize())
        prev = key
    return pd.Series(vals, index=pd.DatetimeIndex(idx)) if vals else None


def pick_revenue(yf_series: pd.Series | None, dart_series: pd.Series | None) -> tuple[pd.Series | None, str | None]:
    """한국 종목 분기 매출 고르기 -> (Series, 'DART'|'yfinance'|None). 최신 분기가 늦은 쪽, 같으면 DART(공시 원본).
    분기 수가 모자라 yoy를 못 내는 쪽은 고르지 않는다(다른 쪽이 낼 수 있으면)."""
    def usable(s):
        return s is not None and len(s) >= MIN_QUARTERS

    def latest(s):
        return pd.Timestamp(s.index[0]).to_period("Q")

    if usable(dart_series) and (not usable(yf_series) or latest(dart_series) >= latest(yf_series)):
        return dart_series, "DART"
    if usable(yf_series):
        return yf_series, "yfinance"
    return (dart_series, "DART") if dart_series is not None else (yf_series, "yfinance" if yf_series is not None else None)
