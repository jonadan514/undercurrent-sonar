"""기업 카드 밸류 위치 (분기 재설계 docs/REDESIGN_SPEC.md 4-3, 5-4).

PSR·PER은 yfinance 값을 그대로 쓰지 않고 select_quarters() 위에서 직접 계산한다
(한국은 yfinance PSR/PER가 자주 비어 있고, US/KR 계산 기준을 통일하기 위해서다 - 4-3).
  PSR = 시가총액 ÷ 최근 4분기 매출 합
  PER = 시가총액 ÷ 최근 4분기 순이익 합 (순이익 합이 0 이하이면 PER 표시 안 함)

입력 계약은 company_change_signals.py와 같다: quarters는 반드시 select_quarters()가
돌려준 리스트여야 한다. 분기 산수(_quarter_map/_shift_quarter)는 그 모듈에도 있지만
따로 복사해 둔다 - 이 저장소는 이런 작은 분기 계산 도우미를 모듈마다 따로 두는
관례다(theme_news_quarterly.py도 자기 것을 따로 갖고 있다). private 함수를 모듈
경계 너머로 가져다 쓰기보다, 각 분석 모듈이 select_quarters() 리스트만으로 자기
계산을 완결짓게 한다.

## "최근 4분기"도 이어붙이지 않는다

매출 흐름(5-1, company_change_signals.py)과 같은 이유다. raw 표에 있는 아무 4개
행이 아니라, 최근 분기에서 연도·분기 산수로 정확히 4개 연속 분기를 요구한다.
중간에 분기가 비면(예: 2026Q3·Q2, 2025Q4만 있고 Q1이 없음) 있는 3개만으로 합계
내지 않는다 - 그러면 "4분기 합"이라는 말과 다른 값이 조용히 나온다.

## 데이터부족 (원칙 4)

  - PSR: 4분기 매출 중 하나라도 없거나, 시가총액이 없거나, 매출 합이 0 이하면 None.
  - PER: 4분기 순이익 중 하나라도 없거나, 순이익 합이 0 이하면 None. SPEC 5-4가
    "흑자 기업만 표시"라고 못박았으니 적자 기업은 계산 실패가 아니라 원래 안
    보여주는 게 맞다 - 그래도 반환 타입은 PSR과 통일해 None으로 둔다(구분해서
    "적자라 표시 안 함"이라는 이유를 따로 알고 싶으면 net_income_sum을 별도로
    확인하면 된다).
  - 테마 3등분: 같은 테마 안에서 PSR 값이 있는 기업이 3곳 미만이면 **테마 전체**가
    데이터부족이다(개별 기업이 아니라 테마 단위 판정 - SPEC 5-4 세 번째 줄).
"""
from __future__ import annotations

CHEAP = "싼 편"
MID = "중간"
EXPENSIVE = "비싼 편"


def _quarter_map(quarters: list[dict]) -> dict[tuple[int, int], dict]:
    """(연도, 분기) -> 그 분기 레코드."""
    return {(int(q["fiscal_year"]), int(q["fiscal_quarter"])): q for q in quarters}


def _shift_quarter(year: int, quarter: int, n: int) -> tuple[int, int]:
    """분기를 n개 앞으로 민다. n=3이면 4분기 합산 창의 가장 오래된 쪽 끝."""
    idx = year * 4 + (quarter - 1) - n
    return idx // 4, idx % 4 + 1


def _last_4q_sum(quarters: list[dict], field: str) -> float | None:
    """최근 분기부터 연속 4개 분기의 field 합. 하나라도 없으면(값이 None이거나 그
    분기 자체가 raw 표에 없으면) None - 있는 것만으로 합 내지 않는다."""
    qmap = _quarter_map(quarters)
    if not qmap:
        return None
    latest_key = max(qmap)
    window = [qmap.get(_shift_quarter(*latest_key, i)) for i in range(4)]
    values = [w.get(field) if w else None for w in window]
    if any(v is None for v in values):
        return None
    return sum(values)


def psr(market_cap: float | None, quarters: list[dict]) -> float | None:
    """PSR = 시가총액 ÷ 최근 4분기 매출 합 (4-3)."""
    if market_cap is None:
        return None
    revenue_sum = _last_4q_sum(quarters, "revenue")
    if revenue_sum is None or revenue_sum <= 0:
        return None
    return market_cap / revenue_sum


def per(market_cap: float | None, quarters: list[dict]) -> float | None:
    """PER = 시가총액 ÷ 최근 4분기 순이익 합. 순이익 합이 0 이하면 None(4-3, 5-4)."""
    if market_cap is None:
        return None
    net_income_sum = _last_4q_sum(quarters, "net_income")
    if net_income_sum is None or net_income_sum <= 0:
        return None
    return market_cap / net_income_sum


def theme_valuation_tiers(psr_by_ticker: dict[str, float | None]) -> dict[str, str | None]:
    """같은 테마 안에서 PSR을 3등분해 싼 편/중간/비싼 편 (5-4).

    psr_by_ticker는 그 테마 소속 기업 전부를 담아야 한다(PSR을 못 구한 기업도 값
    None으로 포함) - 판정 가능 기업만 골라 넘기면 "3곳 미만이면 데이터부족" 기준의
    분모가 달라진다.

    등분 경계는 정렬 후 순위(인덱스)로 나눈다. 백분위수 계산(예: PSR 값에 33%/67%
    분위수를 직접 적용)은 소속 기업 수가 3의 배수가 아니면 경계에서 몇 곳이
    어느 쪽으로 갈지 애매해진다 - 순위 기반이면 항상 명확하게 나뉜다.
    """
    valid = {t: v for t, v in psr_by_ticker.items() if v is not None}
    if len(valid) < 3:
        return {t: None for t in psr_by_ticker}

    ordered = sorted(valid, key=lambda t: valid[t])   # 싼 것(PSR 낮음)부터
    n = len(ordered)
    cheap_end = n // 3
    mid_end = (2 * n) // 3

    tiers: dict[str, str | None] = {t: None for t in psr_by_ticker}
    for i, ticker in enumerate(ordered):
        if i < cheap_end:
            tiers[ticker] = CHEAP
        elif i < mid_end:
            tiers[ticker] = MID
        else:
            tiers[ticker] = EXPENSIVE
    return tiers


# ── 업종 기준 밸류 등급 (2026-11-13, 마스터 플랜 Phase C '섹터 중앙값 계산기') ──────────────
# 예전엔 같은 시장 후보 전체를 PSR 순위로 3등분 - PSR은 업종마다 정상 범위가 달라(소프트웨어 8-10배, 정유 0.5-1배)
# 소프트웨어는 늘 '비싼 편', 에너지는 늘 '싼 편'이었다. 이제 같은 시장·같은 업종의 **유니버스 전체**(통과 후보만이 아니라)
# PSR 분포에서 이 종목 위치로: 가운데 절반(25-75%)보다 아래 '싼 편', 위 '비싼 편', 안 '중간'. 동료 비교 화면의
# '동료보다 낮음/높음'과 같은 잣대. 업종 동료가 PEER_MIN곳 미만이면 섹터로, 그래도 모자라면 None(데이터부족 - 원칙 4).
PEER_MIN = 5


def _quantile(sorted_vals: list[float], p: float) -> float:
    i = (len(sorted_vals) - 1) * p
    lo, hi = int(i), min(int(i) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (i - lo)


def tier_from_levels(own_psr: float | None, levels: list[tuple[str, str, str]], psr_by_key: dict[str, list[float]]) -> dict:
    """levels: [(기준 이름, 묶음 키, 표시 이름)] 좁은 것부터. 값 있는 동료가 PEER_MIN곳 이상인 첫 묶음에서 등급.
    반환: {tier, basis, group, median, n}. 모든 묶음이 모자라면 tier·basis None(데이터부족 - 원칙 4)."""
    for basis, key, name in levels:
        vals = sorted(v for v in psr_by_key.get(key, []) if v is not None and v > 0)
        if key and len(vals) >= PEER_MIN:
            q1, med, q3 = _quantile(vals, 0.25), _quantile(vals, 0.5), _quantile(vals, 0.75)
            tier = None if own_psr is None else CHEAP if own_psr < q1 else EXPENSIVE if own_psr > q3 else MID
            return {"tier": tier, "basis": basis, "group": name, "median": med, "n": len(vals)}
    return {"tier": None, "basis": None, "group": None, "median": None, "n": 0}


def peer_levels(market: str, profile: dict, sector_fallback: str | None = None) -> list[tuple[str, str, str]]:
    """회사 정보(companyProfiles.json 한 종목)로 비교 묶음 순서. 미국: 업종 → 섹터. 한국(2026-11-13): yfinance 업종 →
    KSIC 소분류('g' 첫째) → KSIC 중분류 - 한국은 섹터로 넓히지 않는다(카지노가 자동차·유통과 묶였다)."""
    out: list[tuple[str, str, str]] = []
    if profile.get("i"):
        out.append(("업종", f"i:{profile['i']}", profile["i"]))
    if market == "KR":
        for i, (key, name) in enumerate(profile.get("g") or []):
            out.append(("업종" if i == 0 else "업종 대분류", key, name))
    else:
        sec = profile.get("s") or sector_fallback
        if sec:
            out.append(("섹터", f"s:{sec}", sec))
    return out


def peer_keys(market: str, profile: dict) -> list[str]:
    """이 종목이 들어가는 모든 묶음 키(분포를 쌓을 때)."""
    return [k for _, k, _ in peer_levels(market, profile)]


def peer_valuation_tier(own_psr: float | None, industry: str | None, sector: str | None,
                        psr_by_industry: dict[str, list[float]], psr_by_sector: dict[str, list[float]]) -> dict:
    """업종 → 섹터 두 단계(미국 방식). 반환: {tier, basis('업종'/'섹터'/None), group, median, n}."""
    table = {**{f"i:{k}": v for k, v in psr_by_industry.items()}, **{f"s:{k}": v for k, v in psr_by_sector.items()}}
    levels = [x for x in (("업종", f"i:{industry}", industry), ("섹터", f"s:{sector}", sector)) if x[2]]
    return tier_from_levels(own_psr, levels, table)
