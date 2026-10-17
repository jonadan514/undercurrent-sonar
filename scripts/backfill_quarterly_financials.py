"""Phase A-4/B-2: 승인된 테마 매핑 종목의 분기 매출 데이터 백필.

SPEC: docs/radar/SPEC_phase_a_signals.md §3.1
fundamentals_cache는 원래 연간 재무제표만 캐시한다(Phase 0). 실적 축의
"가속도"(g_t > g_t-1) 계산에는 분기 데이터가 필요한데, 전체 유니버스
(590종목)가 아니라 지금 테마에 승인된 종목만 좁혀서 백필한다(사용자 결정,
옵션 2: 전체 유니버스 캐시 확장보다 필요한 범위만). Phase A는 미국만
다뤘으나, Phase B에서 한국도 같은 방식으로 추가한다 - 한국 티커는 캐시
키(theme_members.ticker)는 접미사 없는 6자리 코드지만 yfinance 조회는
거래소 접미사가 필요해서, watchlist_collector.py와 동일한 관례로
".KS" 우선 조회 후 실패하면 ".KQ"로 재시도한다.

기존 주간 유니버스 갱신의 fetch_status는 건드리지 않는다 - 연간/분기
데이터는 신선도 주기가 다르고, fetch_status를 공유하면 주간 예산제 선정
로직(select_refresh_targets)이 "이미 갱신됐다"고 착각할 위험이 있다.

2026-10-09: 대상을 "테마 소속 + 워치리스트 후보 + 내 워치리스트"로 넓혔다(--scope all, 기본).
워치리스트 분기 영업이익률(compute_watchlist_valuation.py)도 이 캐시를 읽는데, 테마 소속이 아닌
미국 후보 173종목이 비어 있었다. 매주 자동으로 돌기 때문에(토요일) 이미 최신 분기가 있는 종목은
건너뛴다 - 마지막 분기 말일이 FRESH_DAYS 안이면 다음 분기는 아직 끝나지도 않았다.

Usage:
  python scripts/backfill_quarterly_financials.py              # US+KR 둘 다, 테마+워치리스트
  python scripts/backfill_quarterly_financials.py --market KR   # 한쪽만
  python scripts/backfill_quarterly_financials.py --scope themes  # 예전처럼 테마 소속만
  python scripts/backfill_quarterly_financials.py --force       # 최신 분기가 있어도 다시 조회
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import yfinance as yf
from yfinance.exceptions import YFRateLimitError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.db.data_store import get_db
from src.db.fundamentals_cache import ensure_schema, upsert_statement_rows
from src.collectors.kr_kospi_list import yf_suffix as kr_yf_suffix

RATE_LIMIT_BACKOFF = [60, 180, 600]
TICKER_SLEEP_SEC = 1.0
# 분기는 약 91일(13주). 마지막 분기 말일이 이보다 최근이면 다음 분기는 아직 끝나지 않았으니 조회할 게 없다.
FRESH_DAYS = 88


def _log(msg: str) -> None:
    print(f"[quarterly] {msg}")


def get_approved_tickers(conn, market: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT ticker FROM theme_members WHERE approved = 1 AND market = ?",
        (market,),
    ).fetchall()
    return sorted(r[0] for r in rows)


def get_watchlist_tickers(conn, market: str) -> list[str]:
    """워치리스트 후보 + 내 워치리스트 종목. 표가 아직 없는 배포 시점이면 빈 목록."""
    out: set[str] = set()
    for table in ("watchlist_candidates", "my_watchlist"):
        try:
            rows = conn.execute(f"SELECT DISTINCT symbol FROM {table} WHERE market = ?", (market,)).fetchall()
        except Exception as e:  # noqa: BLE001
            _log(f"{market}: {table} 조회 실패({type(e).__name__}) - 건너뜀")
            continue
        out.update(r[0] for r in rows if r[0])
    return sorted(out)


def latest_quarter_ends(conn, market: str) -> dict[str, str]:
    """종목별 캐시에 있는 마지막 분기 말일(YYYY-MM-DD)."""
    rows = conn.execute(
        "SELECT ticker, MAX(period_end) FROM fundamentals_cache "
        "WHERE market = ? AND statement = 'income_quarterly' GROUP BY ticker",
        (market,),
    ).fetchall()
    return {r[0]: r[1] for r in rows if r[1]}


def select_targets(tickers: list[str], latest: dict[str, str], today: date,
                   force: bool = False) -> tuple[list[str], int]:
    """조회할 종목과 건너뛴 수. 캐시가 없거나 마지막 분기 말일이 FRESH_DAYS보다 오래된 종목만 조회."""
    if force:
        return list(tickers), 0
    cutoff = (today - timedelta(days=FRESH_DAYS)).isoformat()
    todo = [t for t in tickers if (latest.get(t) or "") < cutoff]
    return todo, len(tickers) - len(todo)


def yf_symbol_candidates(ticker: str, market: str) -> list[str]:
    """야후 파이낸스 조회용 심볼 후보 - 실패하면 순서대로 다음 걸 시도한다.
    US는 캐시 키와 yfinance 심볼이 동일. KR은 정적 리스트가 아는 거래소
    접미사를 먼저 쓰고, 혹시 목록에 없거나 틀렸을 경우를 대비해 반대쪽도
    폴백으로 시도한다(분기 재무제표는 .KS/.KQ가 동일하지만, 목록에 없는
    티커가 들어올 수 있으므로 폴백은 유지)."""
    if market != "KR":
        return [ticker]
    primary = f"{ticker}{kr_yf_suffix(ticker)}"
    other = f"{ticker}.KQ" if primary.endswith(".KS") else f"{ticker}.KS"
    return [primary, other]


def fetch_quarterly_financials(yf_symbol: str, retries: int = 2):
    """반환: (DataFrame 또는 None, ""|"rate_limited"|"no_data")."""
    rate_limit_attempt = 0
    generic_attempt = 0
    while True:
        try:
            df = yf.Ticker(yf_symbol).quarterly_financials
            if df is None or df.empty:
                return None, "no_data"
            return df, ""
        except Exception as e:
            if isinstance(e, YFRateLimitError):
                if rate_limit_attempt < len(RATE_LIMIT_BACKOFF):
                    wait = RATE_LIMIT_BACKOFF[rate_limit_attempt]
                    rate_limit_attempt += 1
                    _log(f"  {yf_symbol}: rate limit - {wait}초 대기 후 재시도 "
                         f"({rate_limit_attempt}/{len(RATE_LIMIT_BACKOFF)})")
                    time.sleep(wait)
                    continue
                return None, "rate_limited"
            else:
                if generic_attempt < retries:
                    generic_attempt += 1
                    time.sleep(2)
                    continue
                return None, "no_data"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=["US", "KR"], default=None,
                         help="비우면 US+KR 둘 다")
    parser.add_argument("--scope", choices=["all", "themes"], default="all",
                        help="all=테마 소속+워치리스트(기본), themes=테마 소속만")
    parser.add_argument("--force", action="store_true", help="최신 분기가 있어도 다시 조회")
    args = parser.parse_args()
    markets = [args.market] if args.market else ["US", "KR"]

    conn = get_db()
    ensure_schema(conn)

    overall = {"ok": 0, "no_data": 0, "rate_limited": 0}
    for market in markets:
        theme_tickers = get_approved_tickers(conn, market)
        wl_tickers = get_watchlist_tickers(conn, market) if args.scope == "all" else []
        all_tickers = sorted(set(theme_tickers) | set(wl_tickers))
        if not all_tickers:
            _log(f"{market}: 대상 종목이 없음 - 건너뜀")
            continue
        tickers, skipped = select_targets(all_tickers, latest_quarter_ends(conn, market), date.today(), args.force)
        _log(f"{market}: 대상 {len(all_tickers)}종목(테마 {len(theme_tickers)}, 워치리스트 {len(wl_tickers)}, 겹침 제외) "
             f"- 최신 분기 있어 건너뜀 {skipped}, 조회 {len(tickers)}")

        stats = {"ok": 0, "no_data": 0, "rate_limited": 0}
        now = datetime.utcnow().isoformat()
        for i, ticker in enumerate(tickers):
            df, status = None, "no_data"
            for yf_symbol in yf_symbol_candidates(ticker, market):
                df, status = fetch_quarterly_financials(yf_symbol)
                if df is not None or status == "rate_limited":
                    break  # 성공했거나, rate limit이면 다음 접미사도 어차피 막힘
            if df is None:
                stats[status] += 1
                _log(f"[{market} {i + 1}/{len(tickers)}] {ticker}: 실패({status})")
            else:
                n = upsert_statement_rows(conn, ticker, market, "income_quarterly", df, now)
                conn.commit()
                stats["ok"] += 1
                _log(f"[{market} {i + 1}/{len(tickers)}] {ticker}: {n}개 분기 저장")
            time.sleep(TICKER_SLEEP_SEC)

        _log(f"{market} 완료 - {stats}")
        for k in overall:
            overall[k] += stats[k]

    conn.close()
    _log(f"전체 완료 - {overall}")
    # 20종목 넘게 시도했는데 하나도 못 받았으면 출처(야후) 쪽 문제 - 성공으로 끝나면 아무도 모른다(2026-10-17).
    # 몇 종목만 남은 주(실적 시즌 밖, 늘 비는 신형 코드 6개 등)는 0건이어도 정상이라 문턱을 둔다.
    attempted = sum(overall.values())
    if attempted >= 20 and overall["ok"] == 0:
        _log(f"{attempted}종목 시도, 성공 0 - 실패로 끝낸다")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
