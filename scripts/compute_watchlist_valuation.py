"""워치리스트 후보에 밸류 지표(PSR/PER)와 성장 지표(매출 CAGR 등)를 채운다.

워치리스트는 함정 필터를 통과한 "재무가 탄탄한 종목" 목록인데, 화면에 보이는 지표가
F-Score·부채비율·이자보상뿐이라 **전부 품질 지표**였다. 장기 투자자가 새 아이디어를
찾을 때 가장 자연스러운 진입점인 "탄탄한데 싸기도 한 것"을 이 화면에서는 찾을 수 없었다
(밸류, 2026-09-24). 그런데 밸류만으로는 부족하다 - 무차입 흑자인데 매출이 3년째
줄어드는 기업도 함정 필터를 통과하고 시장이 주가를 깎아놔서 "싼 편"으로 뜬다.
성장 축(2026-09-30, docs/SPEC_watchlist_growth.md)이 그 가치 함정을 드러낸다.

파일 이름이 "valuation"인데 성장까지 계산하는 게 정확하지 않지만, 같은 후보 집합을
읽고 같은 표에 쓰는 작업이라 스크립트를 분리하지 않는다(SPEC 5-2 - 이름을 바꾸면
워크플로 파일도 바꿔야 하고 workflow_dispatch가 기본 브랜치의 YAML만 찾아 main
재등록이 또 필요해진다).

계산은 새로 만들지 않는다 - 분기 재설계에서 쓰는 것과 **같은 함수**
(`src/analyzers/company_valuation.py`, `src/analyzers/company_growth.py`)를 그대로
쓴다. 두 곳에서 다르게 계산하면 같은 종목이 화면마다 다른 값으로 보인다.

  PSR = 시가총액 ÷ 최근 4분기 매출 합
  PER = 시가총액 ÷ 최근 4분기 순이익 합 (순이익 합이 0 이하면 표시 안 함)
  매출 3년 CAGR = (최신 연매출 / 3년전 연매출) ** (1/3) - 1
  최근 1년      = 최신 연매출 / 직전 연매출 - 1

시가총액은 watchlist_candidates에 이미 있는 값을 쓴다(스크리닝 시점 기준) - 분기
화면이 fetch_status.info_payload를 쓰는 것과 출처가 다르지만, 워치리스트 행의 다른
숫자들과 같은 시점이어야 화면 안에서 앞뒤가 맞는다.

## 밸류는 3등분, 성장은 절대 기준 - 등급 계산 방식이 서로 다르다

밸류(PSR)는 "비싼지 싼지"에 절대 기준이 없어 **같은 시장 후보 전체 안에서** 순위로
3등분한다(분기 화면은 테마 안에서 3등분 - SPEC 5-4). 성장은 다르다. 실측
(docs/SPEC_watchlist_growth.md 2장)으로 후보의 86-93%가 이미 양의 성장 중인 걸
확인했다 - 순위로 3등분하면 +3%로 성장 중인 기업에 "역성장" 라벨이 붙는다. 그래서
성장 등급(`growth_tier`)은 절대 기준(0%, 10%)을 쓴다. 같은 종목이 밸류는 상대
등급, 성장은 절대 등급으로 나오는 게 의도한 비대칭이다.

## 스크리닝 뒤에 반드시 다시 돌려야 한다

run_watchlist_screen.py는 매주 해당 시장 행을 DELETE하고 새로 INSERT한다. 그러면
여기서 채운 값도 같이 사라진다. 그래서 run_watchlist_screen.py main()이 Turso
업로드 직후 이 스크립트의 run()을 호출한다. 이 파일을 직접 실행하는 건 수동 보정이나
지금처럼 처음 채워 넣을 때를 위한 것이다.

Usage:
  python scripts/compute_watchlist_valuation.py
  python scripts/compute_watchlist_valuation.py --market KR
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.analyzers.company_growth import (quarterly_margin_change, quarterly_revenue_yoy, ttm_revenue_yoy,
                                           growth_tier as calc_growth_tier,
                                           operating_margin_direction,
                                           revenue_cagr, revenue_yoy)
from src.analyzers.company_valuation import per as calc_per, psr as calc_psr, theme_valuation_tiers
from src.analyzers.company_cashflow import fcf_yield
from src.db.data_store import get_db
from src.db.fundamentals_cache import get_cached_financials_bulk
from src.db.quarterly_financials import select_quarters_bulk
from src.db.turso_http import execute_many, get_credentials

# watchlist_candidates에 뒤늦게 붙이는 컬럼. DDL(CREATE TABLE IF NOT EXISTS)만 고치면
# 이미 있는 표에는 반영되지 않아서, theme_signals.py의 LATE_COLUMNS와 같은 방식으로
# ALTER TABLE을 try/except로 감싸 돌린다.
LATE_COLUMNS = [
    ("psr", "REAL"), ("per", "REAL"), ("valuation_tier", "TEXT"),
    ("revenue_cagr_3y", "REAL"), ("revenue_yoy", "REAL"),
    ("op_margin_direction", "TEXT"), ("growth_tier", "TEXT"),
    # 분기 영업이익률 전년동기 비교(2026-10-05) - 연간 3년 비교(op_margin_direction)보다 이른 신호
    ("op_margin_q_now", "REAL"), ("op_margin_q_change", "REAL"), ("op_margin_q_status", "TEXT"),
    # 최근 분기 매출 전년동기 대비(2026-10-09) - 3년 CAGR 판정 옆에 따로 보여 주는 "지금 흐름"
    ("rev_q_yoy", "REAL"), ("rev_q_tier", "TEXT"), ("rev_q_quarter", "TEXT"),
    # 최근 4개 분기 합 대 직전 4개 분기 합(TTM, 2026-10-09) - quarterly_financials_raw 연속 8분기가 있을 때만
    ("rev_ttm_yoy", "REAL"), ("rev_ttm_tier", "TEXT"), ("rev_ttm_quarter", "TEXT"),
    # FCF 수익률(2026-10-19) - 3년 평균 FCF / 시가총액, 상세 카드 전용(등급 없음, company_cashflow.py)
    ("fcf_yield_3y", "REAL"), ("fcf_yield_latest", "REAL"), ("fcf_negative_years", "INTEGER"),
    ("fcf_latest_year", "TEXT"),
]

UPDATE_SQL = (
    "UPDATE watchlist_candidates SET psr = ?, per = ?, valuation_tier = ?, "
    "revenue_cagr_3y = ?, revenue_yoy = ?, op_margin_direction = ?, growth_tier = ?, "
    "op_margin_q_now = ?, op_margin_q_change = ?, op_margin_q_status = ?, "
    "rev_q_yoy = ?, rev_q_tier = ?, rev_q_quarter = ?, "
    "rev_ttm_yoy = ?, rev_ttm_tier = ?, rev_ttm_quarter = ?, "
    "fcf_yield_3y = ?, fcf_yield_latest = ?, fcf_negative_years = ?, fcf_latest_year = ? "
    "WHERE market = ? AND symbol = ?"
)
BATCH = 50   # push_to_turso()와 같은 크기


def _log(msg: str) -> None:
    print(f"[wl-value] {msg}", flush=True)


def ensure_columns(conn) -> None:
    for name, coltype in LATE_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE watchlist_candidates ADD COLUMN {name} {coltype}")
        except Exception:
            pass   # 이미 있는 컬럼 - 정상
    conn.commit()


def load_candidates(conn, market: str) -> list[dict]:
    rows = conn.execute(
        "SELECT symbol, market_cap FROM watchlist_candidates WHERE market = ?", (market,)
    ).fetchall()
    # Turso는 REAL도 문자열로 돌려준다 - 문자열을 시가총액으로 나누면 죽는다.
    return [
        {"symbol": r[0], "market_cap": float(r[1]) if r[1] is not None else None}
        for r in rows
    ]


def income_periods(financials_df) -> list[tuple[str, dict]]:
    """get_cached_financials_bulk()가 주는 연차 손익 DataFrame(_to_df() 출력 -
    컬럼=회계기간 Timestamp, 최신순) -> company_growth가 기대하는
    [(period_end: str, data: dict), ...] 형태로 바꾼다.

    dropna()를 거치는 이유: DataFrame은 여러 회계기간의 계정을 합쳐 만들어서,
    어떤 기간에 없던 계정은 그 열에서 NaN으로 채워진다. NaN은 None이 아니라서
    company_growth._pick()의 `is not None` 체크를 그냥 통과해 버린다 - 여기서
    미리 걸러내야 한다.
    """
    if financials_df is None or financials_df.empty:
        return []
    out = []
    for col in financials_df.columns:
        period_end = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
        out.append((period_end, financials_df[col].dropna().to_dict()))
    return out


def write_updates(conn, market: str, updates: list[tuple]) -> None:
    """updates: (psr, per, tier, cagr_3y, yoy, op_dir, growth_tier, om_now, om_change, om_status,
    rq_yoy, rq_tier, rq_quarter, ttm_yoy, ttm_tier, ttm_quarter,
    fcf_yield_3y, fcf_yield_latest, fcf_negative_years, fcf_latest_year, symbol) 목록.

    후보가 시장당 100종목이 넘어서 _TursoConn.execute()로 한 줄씩 보내면 UPDATE 하나마다
    HTTP 왕복이 생긴다 - push_to_turso()와 같이 pipeline 배치로 묶는다.
    """
    if get_credentials():
        statements = [(UPDATE_SQL, [*row, market, symbol]) for *row, symbol in updates]
        for i in range(0, len(statements), BATCH):
            execute_many(statements[i:i + BATCH])
        return
    # 로컬 sqlite(개발·테스트)에서는 왕복 비용이 없으니 한 줄씩 보낸다. executemany는
    # 쓰지 않는다 - 운영 연결(_TursoConn)에도, 테스트 fixture에도 그 메서드가 없다.
    for *row, symbol in updates:
        conn.execute(UPDATE_SQL, (*row, market, symbol))
    conn.commit()


def run(conn, markets: list[str]) -> None:
    for market in markets:
        candidates = load_candidates(conn, market)
        if not candidates:
            _log(f"{market}: 후보 없음 - 건너뜀")
            continue

        symbols = [c["symbol"] for c in candidates]
        quarters_by_ticker = select_quarters_bulk(conn, symbols, market)
        # 연차 재무제표 일괄 조회 - 종목마다 개별 조회하면 275종목이면 275번 왕복이
        # 생긴다(SPEC 5-2, get_cached_financials_bulk()의 존재 이유와 같다).
        financials_by_ticker = get_cached_financials_bulk(conn, symbols)

        psr_by_ticker: dict[str, float | None] = {}
        per_by_ticker: dict[str, float | None] = {}
        cagr_by_ticker: dict[str, float | None] = {}
        yoy_by_ticker: dict[str, float | None] = {}
        op_dir_by_ticker: dict[str, str | None] = {}
        om_by_ticker: dict[str, dict] = {}
        rq_by_ticker: dict[str, dict] = {}
        ttm_by_ticker: dict[str, dict] = {}
        fcf_by_ticker: dict[str, dict] = {}
        for c in candidates:
            sym = c["symbol"]
            quarters = quarters_by_ticker.get(sym, [])
            psr_by_ticker[sym] = calc_psr(c["market_cap"], quarters)
            ttm_by_ticker[sym] = ttm_revenue_yoy(quarters) or {}
            per_by_ticker[sym] = calc_per(c["market_cap"], quarters)

            cached = financials_by_ticker.get(sym)
            periods = income_periods(cached["financials"]) if cached else []
            cagr_by_ticker[sym] = revenue_cagr(periods)
            yoy_by_ticker[sym] = revenue_yoy(periods)
            op_dir_by_ticker[sym] = operating_margin_direction(periods)
            om_by_ticker[sym] = (quarterly_margin_change(cached.get("financials_quarterly")) if cached else None) or {}
            rq_by_ticker[sym] = (quarterly_revenue_yoy(cached.get("financials_quarterly")) if cached else None) or {}
            # 현금흐름표도 손익과 같은 모양(컬럼=회계기간)이라 같은 변환을 쓴다.
            fcf_by_ticker[sym] = fcf_yield(income_periods(cached.get("cashflow")) if cached else [],
                                           c["market_cap"])

        # 밸류: 같은 시장 후보 전체 안에서 3등분(위 모듈 설명 참고 - 분기 화면은 테마 안에서 나눈다).
        tiers = theme_valuation_tiers(psr_by_ticker)
        # 성장: 절대 기준이라 등급을 매기는 데 다른 종목 값이 필요 없다 - 종목별로 독립 계산.
        growth_tiers = {sym: calc_growth_tier(cagr_by_ticker[sym]) for sym in cagr_by_ticker}

        write_updates(conn, market, [
            (psr_by_ticker[c["symbol"]], per_by_ticker[c["symbol"]], tiers[c["symbol"]],
             cagr_by_ticker[c["symbol"]], yoy_by_ticker[c["symbol"]],
             op_dir_by_ticker[c["symbol"]], growth_tiers[c["symbol"]],
             om_by_ticker[c["symbol"]].get("now"), om_by_ticker[c["symbol"]].get("change"),
             om_by_ticker[c["symbol"]].get("status"),
             rq_by_ticker[c["symbol"]].get("yoy"), rq_by_ticker[c["symbol"]].get("tier"),
             rq_by_ticker[c["symbol"]].get("quarter"),
             ttm_by_ticker[c["symbol"]].get("yoy"), ttm_by_ticker[c["symbol"]].get("tier"),
             ttm_by_ticker[c["symbol"]].get("quarter"),
             fcf_by_ticker[c["symbol"]]["yield_3y"], fcf_by_ticker[c["symbol"]]["yield_latest"],
             fcf_by_ticker[c["symbol"]]["negative_years"], fcf_by_ticker[c["symbol"]]["latest_year"],
             c["symbol"])
            for c in candidates
        ])

        have_psr = sum(1 for v in psr_by_ticker.values() if v is not None)
        have_per = sum(1 for v in per_by_ticker.values() if v is not None)
        have_ttm = sum(1 for v in ttm_by_ticker.values() if v.get("yoy") is not None)
        _log(f"{market}: 최근 4분기 매출 비교(연속 8분기) 가능 {have_ttm}종목")
        _log(f"{market}: 후보 {len(candidates)}종목 / PSR {have_psr} / PER {have_per}"
             f" (PER은 흑자 기업만) / 분기 재무 있는 종목 {len(quarters_by_ticker)}")
        if have_psr:
            vals = sorted(v for v in psr_by_ticker.values() if v is not None)
            _log(f"  PSR 최소 {vals[0]:.2f} / 중앙 {vals[len(vals) // 2]:.2f} / 최대 {vals[-1]:.2f}")

        fcf3 = sorted(v["yield_3y"] for v in fcf_by_ticker.values() if v["yield_3y"] is not None)
        _log(f"  FCF 수익률(3년 평균) 계산됨 {len(fcf3)}/{len(candidates)}")
        if fcf3:
            neg = sum(1 for v in fcf_by_ticker.values() if (v["negative_years"] or 0) > 0)
            _log(f"    최소 {fcf3[0]*100:.1f}% / 중앙 {fcf3[len(fcf3)//2]*100:.1f}% / 최대 {fcf3[-1]*100:.1f}%"
                 f" / 3년 중 음수 해가 있는 종목 {neg}")

        have_cagr = sum(1 for v in cagr_by_ticker.values() if v is not None)
        _log(f"  매출 3년 CAGR 계산됨 {have_cagr}/{len(candidates)}")
        if have_cagr:
            vals = sorted(v for v in cagr_by_ticker.values() if v is not None)
            _log(f"    최소 {vals[0]*100:.1f}% / 중앙 {vals[len(vals)//2]*100:.1f}% / 최대 {vals[-1]*100:.1f}%")
            dist = Counter(growth_tiers[s] for s in growth_tiers if growth_tiers[s] is not None)
            _log(f"    등급 분포: {dict(dist)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default=None, choices=["KR", "US"], help="비우면 둘 다")
    args = ap.parse_args()

    conn = get_db()
    try:
        ensure_columns(conn)
        run(conn, [args.market] if args.market else ["KR", "US"])
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
