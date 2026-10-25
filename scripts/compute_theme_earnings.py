"""Phase A-4/B-2: 테마별 실적 축 계산.

SPEC: docs/radar/SPEC_phase_a_signals.md §3
Phase A는 미국 시장만 대상이었으나, Phase B에서 한국도 같은 로직으로
처리한다(시장별로 그 시장의 승인된 소속 기업만 순회). 분기 재무제표는
scripts/backfill_quarterly_financials.py로 미리 채워져 있어야 한다
(승인된 테마 매핑 종목만 대상으로 함).

실적 축은 주간 신호가 아니지만(분기에 한 번만 바뀜), 매주 도는 파이프라인이
현재 주 행에 같은 값을 다시 채워 넣는다 - 화면이 그 주의 세 축을 한 행에서
보게 하기 위함(earn_as_of로 "이 값은 지난 분기 것"임을 표시).

Usage:
  python scripts/compute_theme_earnings.py                       # 전체 US+KR 테마
  python scripts/compute_theme_earnings.py --theme-id nuclear_smr  # 특정 테마만
  python scripts/compute_theme_earnings.py --include-peripheral   # peripheral 포함(옵션)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.db.data_store import get_db
from src.db.fundamentals_cache import ensure_schema as ensure_fundamentals_schema, get_cached_financials_bulk
from src.db.theme_signals import (ensure_schema, signal_week_monday, get_approved_theme_members, get_surprises,
                                   upsert_earn_signal, upsert_member_earnings, upsert_member_fcf)
from analyzers.theme_earnings import (classify_company_earnings, compute_earn_signal,
                                      reference_growth_for_market, yoy_growth)
from analyzers.company_growth import quarterly_margin_change
from collectors.watchlist_collector import get_kr_universe, get_us_universe
from collectors.earnings_surprise_collector import summarize_theme
from src.analyzers.company_cashflow import fcf_yield
from src.analyzers.trap_filter import FINANCIAL_SECTORS

sys.path.insert(0, str(ROOT / "scripts"))
from compute_watchlist_valuation import income_periods  # noqa: E402 - 연차 DataFrame -> [(기간, dict)] 변환을 같이 쓴다

THEMES_YAML = ROOT / "config" / "themes.yaml"


def _log(msg: str) -> None:
    print(f"[earn] {msg}")


def load_active_themes(theme_ids: list[str] | None) -> tuple[list[dict], dict]:
    with open(THEMES_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    themes = [t for t in data["themes"] if t.get("status") == "active"]
    if theme_ids:
        wanted = set(theme_ids)
        themes = [t for t in themes if t["id"] in wanted]
    return themes, data.get("config", {})


def member_fcf(data: dict | None, universe_cap: float | None) -> dict:
    """테마 동료 비교(종목 상세)용 FCF 수익률 - 워치리스트 상세 카드와 같은 계산(company_cashflow.fcf_yield).
    시가총액은 넘겨받은 값(워치리스트 후보 → 한국 유니버스 파일 순) 먼저, 없으면 캐시된 info.marketCap. 금융업은 계산하지 않는다
    (예금·보험료 흐름이 영업현금흐름에 섞인다 - compute_watchlist_valuation과 같은 기준). 못 구하면 None(데이터부족)."""
    none = {"yield_3y": None, "negative_years": None}
    if not data:
        return none
    info = data.get("info") or {}
    if any(sec in str(info.get("sector") or "") for sec in FINANCIAL_SECTORS):
        return none
    cap = universe_cap or info.get("marketCap")
    try:
        cap = float(cap) if cap else None
    except (TypeError, ValueError):
        cap = None
    r = fcf_yield(income_periods(data.get("cashflow")), cap)
    return {"yield_3y": r["yield_3y"], "negative_years": r["negative_years"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme-id", nargs="*", default=None, help="특정 테마만 (비우면 전체)")
    parser.add_argument("--include-peripheral", action="store_true",
                         help="linkage=peripheral도 포함 (SPEC §3.2 옵션 - 기본은 제외)")
    parser.add_argument("--week-start", default=None,
                         help="기준 주 월요일(YYYY-MM-DD). 비우면 오늘이 속한 주 - "
                              "평시 크론(일요일 밤)은 방금 끝난 주를 잡지만, 주 초에 "
                              "수동 실행하면 아직 데이터가 없는 새 주를 잡게 되므로 "
                              "그때 명시적으로 지정하기 위한 옵션.")
    args = parser.parse_args()

    themes, config = load_active_themes(args.theme_id)
    if not themes:
        _log("대상 테마 없음")
        sys.exit(1)
    thresholds = config.get("earnings_thresholds", {"strong_up": 0.70, "up": 0.55, "down": 0.45})
    linkages = ("direct", "partial", "peripheral") if args.include_peripheral else ("direct", "partial")

    conn = get_db()
    ensure_fundamentals_schema(conn)
    ensure_schema(conn)

    week_start = args.week_start or signal_week_monday(date.today()).isoformat()

    # (테마, 시장) 쌍별 소속 기업을 먼저 다 모아서, 필요한 티커 전체(US+KR
    # 합쳐)에 대해 재무 캐시를 한 번만 벌크 조회한다 - 개별 조회하면 겹치는
    # 종목(여러 테마 소속)을 중복으로 왕복하게 된다(SPEC §7과 동일한 "배치로"
    # 원칙). US 티커(알파벳)와 KR 티커(6자리 숫자)는 문자열이 겹칠 일이 없어
    # 하나의 집합으로 안전하게 합칠 수 있다.
    members_by_theme_market: dict[tuple[str, str], list[dict]] = {}
    all_tickers: set[str] = set()
    for theme in themes:
        for market in theme.get("markets", []):
            if market not in ("US", "KR"):
                continue
            members = get_approved_theme_members(conn, theme["id"], market, linkages)
            if not members:
                continue
            members_by_theme_market[(theme["id"], market)] = members
            all_tickers.update(m["ticker"] for m in members)

    _log(f"대상 (테마,시장) {len(members_by_theme_market)}개, "
         f"소속 기업(중복제거) {len(all_tickers)}개, 기준 주 {week_start}")

    # 기준 성장률의 표본은 테마 소속이 아니라 **시장 유니버스 전체**다(2026-09-21 수정).
    # 소속 기업이 곧 표본이면 절반이 자동으로 기준 위에 놓여 개선 비율이 0.5 근처로 쏠린다.
    universe_by_market: dict[str, list[str]] = {}
    universe_cap: dict[str, float] = {}   # FCF 수익률용 시가총액(한국 유니버스 파일에만 있다)
    for market, getter in (("US", get_us_universe), ("KR", get_kr_universe)):
        if not any(mk == market for _, mk in members_by_theme_market):
            continue
        try:
            items = getter()
            universe_by_market[market] = [it["symbol"] for it in items]
            universe_cap.update({it["symbol"]: it["market_cap"] for it in items if it.get("market_cap")})
        except Exception as e:  # noqa: BLE001 - 유니버스를 못 읽으면 소속 기업만으로 폴백한다
            _log(f"{market} 유니버스 로드 실패 {type(e).__name__}: {str(e)[:80]} - 소속 기업만으로 기준선 계산")
            universe_by_market[market] = []

    needed = set(all_tickers)
    for tickers in universe_by_market.values():
        needed.update(tickers)

    financials = get_cached_financials_bulk(conn, sorted(needed))
    revenue_by_ticker = {}
    margin_by_ticker: dict[str, dict | None] = {}   # 분기 영업이익률 전년동기 비교(소속 기업 표시용, 실적 축에는 안 씀)
    for ticker, data in financials.items():
        if data is None:
            revenue_by_ticker[ticker] = None
            continue
        q_df = data.get("financials_quarterly")
        margin_by_ticker[ticker] = quarterly_margin_change(q_df)
        if q_df is None or q_df.empty or "Total Revenue" not in q_df.index:
            revenue_by_ticker[ticker] = None
            continue
        revenue_by_ticker[ticker] = q_df.loc["Total Revenue"].dropna()

    # 기준 성장률(시장 중앙값)은 반드시 시장별로 따로 낸다 - 미국과 한국의
    # 성장률 분포가 다른데 한 덩어리로 중앙값을 내면 한쪽이 통째로 위/아래로
    # 쏠린다(주가 축에서 시장별 지수를 쓰는 것과 같은 이유).
    reference_by_market: dict[str, float | None] = {}
    for market in {m for _, m in members_by_theme_market}:
        sample = universe_by_market.get(market) or sorted({
            m["ticker"] for (tid, mk), members in members_by_theme_market.items()
            if mk == market for m in members})   # 유니버스를 못 읽었을 때만 소속 기업으로 폴백
        ref = reference_growth_for_market({t: revenue_by_ticker.get(t) for t in sample}, market)
        reference_by_market[market] = ref
        usable = sum(1 for t in sample if revenue_by_ticker.get(t) is not None)
        if ref is None:
            _log(f"{market}: 표본 부족으로 중앙값 산출 불가 - 절대 기준(0%)으로 폴백 "
                 f"(유니버스 {len(sample)}개 중 매출 확보 {usable}개)")
        else:
            _log(f"{market}: 기준 성장률(시장 유니버스 중앙값) {ref*100:.1f}% "
                 f"(유니버스 {len(sample)}개 중 매출 확보 {usable}개)")

    # 실적 발표 서프라이즈(참고 수치). scripts/collect_earnings_surprise.py가 쌓아둔 값만
    # 읽는다 - 여기서 새로 조회하지 않는다(종목별 호출이라 수집은 따로 예산제로 돈다).
    surprises = get_surprises(conn, sorted(all_tickers))
    _log(f"서프라이즈 보유 {len(surprises)}/{len(all_tickers)}종목")

    # 시가총액은 워치리스트 후보 값이 있으면 그것부터 - 같은 종목의 상세 카드 FCF 수익률(compute_watchlist_valuation)과 숫자가 같게
    try:
        for sym, cap in conn.execute("SELECT symbol, market_cap FROM watchlist_candidates WHERE market_cap IS NOT NULL").fetchall():
            universe_cap[sym] = float(cap)
    except Exception as e:  # noqa: BLE001 - 후보 표가 없으면 유니버스·info 값으로
        _log(f"후보 시가총액 조회 실패 {type(e).__name__} - 유니버스·캐시 값으로")
    fcf_by_ticker = {t: member_fcf(financials.get(t), universe_cap.get(t)) for t in all_tickers}
    _log(f"FCF 수익률(3년 평균) 계산 {sum(1 for v in fcf_by_ticker.values() if v['yield_3y'] is not None)}/{len(all_tickers)}종목")

    now = datetime.utcnow().isoformat()
    for (theme_id, market), members in members_by_theme_market.items():
        result = compute_earn_signal(members, revenue_by_ticker, thresholds,
                                      reference_by_market.get(market))
        surprise = summarize_theme(members, surprises)
        run_id = members[0]["run_id"]
        sp_str = (f"{surprise['beat']}/{surprise['n']}" if surprise["n"] else "-")
        _log(f"{theme_id}({market}): members={result['members']} "
             f"기준초과={result['improved']} insufficient={result['insufficient']} "
             f"ratio={result['ratio']} arrow={result['arrow']} as_of={result['as_of']} "
             f"서프라이즈 상회={sp_str}")

        upsert_earn_signal(
            conn, theme_id, market, week_start,
            result["members"], result["improved"], result["insufficient"],
            result["ratio"], result["arrow"], result["as_of"],
            result["members"], run_id, now, surprise,
        )
        # 기업별 매출 성장률·판정도 같은 주 키로 남긴다(테마 흐름 이력 화면). 판정 기준은 테마 집계와 같은 값.
        ref = reference_by_market.get(market)
        member_rows = []
        for m in members:
            rev = revenue_by_ticker.get(m["ticker"])
            status, q_label = classify_company_earnings(rev, 0.0 if ref is None else ref)
            om = margin_by_ticker.get(m["ticker"]) or {}
            member_rows.append((theme_id, market, week_start, m["ticker"], yoy_growth(rev), q_label, status,
                                om.get("now"), om.get("change"), om.get("status"), now))
        upsert_member_earnings(conn, member_rows)
        upsert_member_fcf(conn, [(theme_id, market, week_start, m["ticker"], fcf_by_ticker[m["ticker"]]["yield_3y"],
                                  fcf_by_ticker[m["ticker"]]["negative_years"], now) for m in members])
        conn.commit()

    conn.close()
    _log("완료")


if __name__ == "__main__":
    main()
