"""SEC EDGAR XBRL(companyfacts)에서 미국 기업 분기 매출·영업이익·순이익을 뽑는다 (2026-10-09 사용자 결정, 2026-10-17 구현).

왜: yfinance 무료 분기 재무는 5분기뿐이라 "최근 4개 분기 합 대 직전 4개 분기 합"(연속 8분기)을 못 낸다.
SEC companyfacts는 회사가 공시한 XBRL 값 전체를 준다(무료, 키 없음, User-Agent에 연락처 필수).

계산 규칙 (한국 DART와 같은 성격)
  - 분기 값: 기간이 80-100일인 값. 같은 기간이 여러 공시에 있으면 가장 늦게 제출된 값(정정 반영).
  - 4분기: 10-K에는 연간 값만 있다 -> 연간(350-380일) - 그 안의 1-3분기 합. 세 분기가 다 있을 때만(derived=annual_minus_9m).
  - 계정: 회사마다 매출 계정 이름이 다르다 -> 후보 계정 중 기준일 이후 분기를 가장 많이 가진 계정 하나만 쓴다
    (계정을 분기마다 섞으면 정의가 다른 숫자가 이어 붙을 수 있다).
  - 분기 번호: 분기말 날짜의 달력 분기(collect_us_quarterly_financials.quarter_of와 같은 규칙) - 같은 표의
    yfinance 행과 같은 (연도, 분기)로 맞물리게 한다.
숫자는 공시 값 그대로이고 4분기만 뺄셈 산출이다(원칙 2).
"""
from __future__ import annotations

from datetime import date, timedelta

REVENUE_CONCEPTS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenuesNetOfInterestExpense",
)
OPERATING_INCOME_CONCEPTS = ("OperatingIncomeLoss",)
NET_INCOME_CONCEPTS = ("NetIncomeLoss", "ProfitLoss")

QUARTER_DAYS = (80, 100)
ANNUAL_DAYS = (350, 380)
SINCE = date(2023, 1, 1)   # 이보다 이른 분기말은 버린다(연속 8분기에 넉넉한 범위)


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def quarter_of(end: date) -> tuple[int, int]:
    return end.year, (end.month - 1) // 3 + 1


def _latest_by_period(items: list[dict]) -> dict[tuple[date, date], float]:
    """(시작, 끝) -> 가장 늦게 제출된 값."""
    best: dict[tuple[date, date], tuple[str, float]] = {}
    for it in items:
        if not it.get("start") or not it.get("end") or it.get("val") is None:
            continue
        key = (_d(it["start"]), _d(it["end"]))
        filed = str(it.get("filed") or "")
        cur = best.get(key)
        if cur is None or filed >= cur[0]:
            best[key] = (filed, float(it["val"]))
    return {k: v for k, (_, v) in best.items()}


def concept_series(items: list[dict]) -> dict[date, tuple[float, str]]:
    """한 계정의 USD 값 목록 -> {분기말: (값, 'reported'|'annual_minus_9m')}."""
    periods = _latest_by_period(items)
    quarters: dict[date, tuple[date, float]] = {}
    annuals: list[tuple[date, date, float]] = []
    for (start, end), val in periods.items():
        days = (end - start).days
        if QUARTER_DAYS[0] <= days <= QUARTER_DAYS[1]:
            quarters[end] = (start, val)
        elif ANNUAL_DAYS[0] <= days <= ANNUAL_DAYS[1]:
            annuals.append((start, end, val))
    out = {end: (val, "reported") for end, (_, val) in quarters.items()}
    for start, end, val in annuals:
        if end in out:
            continue
        inside = [v for e, (s, v) in quarters.items() if s >= start - timedelta(days=7) and e <= end - timedelta(days=20) and e > start]
        if len(inside) == 3:
            out[end] = (val - sum(inside), "annual_minus_9m")
    return out


def pick_series(us_gaap: dict, concepts: tuple[str, ...]) -> dict[date, tuple[float, str]]:
    """후보 계정 중 SINCE 이후 분기를 가장 많이 가진 계정 하나(동률이면 앞 순서)."""
    best: dict[date, tuple[float, str]] = {}
    best_n = 0
    for c in concepts:
        items = ((us_gaap.get(c) or {}).get("units") or {}).get("USD") or []
        s = concept_series(items)
        n = sum(1 for e in s if e >= SINCE)
        if n > best_n:
            best, best_n = s, n
    return best


def quarterly_values(companyfacts: dict) -> dict[tuple[int, int], dict]:
    """companyfacts JSON -> {(연도, 분기): {revenue, operating_income, net_income, derived, fs_div: None}}.
    매출이 없는 분기는 넣지 않는다(4분기 합 비교·PSR이 매출을 쓴다)."""
    us_gaap = (companyfacts.get("facts") or {}).get("us-gaap") or {}
    rev = pick_series(us_gaap, REVENUE_CONCEPTS)
    op = pick_series(us_gaap, OPERATING_INCOME_CONCEPTS)
    net = pick_series(us_gaap, NET_INCOME_CONCEPTS)
    out: dict[tuple[int, int], dict] = {}
    for end in sorted(rev):
        if end < SINCE:
            continue
        key = quarter_of(end)
        # 52/53주 회계연도에서 두 분기말이 같은 달력 분기에 떨어지면 늦은 쪽(sorted라 덮어씀)
        r_val, r_how = rev[end]
        derived = "annual_minus_9m" if r_how == "annual_minus_9m" else "reported"
        out[key] = {
            "revenue": r_val,
            "operating_income": (op.get(end) or (None,))[0],
            "net_income": (net.get(end) or (None,))[0],
            "derived": derived,
            "fs_div": None,
        }
    return out
