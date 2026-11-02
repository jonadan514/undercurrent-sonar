"""한국 기업 분기 재무(매출·영업이익·순이익)를 DART에서 모아 quarterly_financials에 저장한다.

분기 재설계 docs/REDESIGN_SPEC.md 4-1. 계산 규칙은 src/collectors/dart_financials.py.

최근 5분기가 필요하므로 올해·작년 보고서를 먼저 받고, 5분기가 안 모이면 재작년까지 받는다
(연초에는 작년 사업보고서가 아직 안 나와서 최신 분기가 재작년 3분기일 수 있다).
기업당 8-12회 호출이라 KR 유니버스 664종목이면 약 6,000-8,000회 - DART 일일 한도(2만) 안이다.

2026-09-23 표본 실측(5종목, 전부 8회 호출로 끝남): 종목당 약 15.6초. 664종목 전체를
한 번에 돌리면 약 173분으로 GitHub Actions 워크플로 제한(180분)에 거의 닿는다 - 재작년
fallback(종목당 호출 50% 추가)이 몇 종목만 걸려도 넘길 수 있다. --offset/--limit으로
나눠 돌린다(뉴스 백필이 날짜 구간을 나눈 것과 같은 이유).

Usage:
  python scripts/collect_kr_quarterly_financials.py --tickers 005930 086520   # 몇 종목만 + 표 출력
  python scripts/collect_kr_quarterly_financials.py                           # KR 유니버스 전체
  python scripts/collect_kr_quarterly_financials.py --offset 220 --limit 220  # 이어서 한 구간만
  python scripts/collect_kr_quarterly_financials.py --watchlist --years 3     # 워치리스트만, 3개 연도 보고서

2026-10-09: --watchlist(워치리스트 후보 + 내 워치리스트)와 --years 추가. 최근 4개 분기 합을
직전 4개 분기 합과 비교(company_growth.ttm_revenue_yoy)하려면 연속 8분기가 필요해 재작년 보고서까지 받는다(--years 3).
매주 토요일 자동 실행은 --watchlist --years 2(올해·작년 보고서) - 새 분기만 이어 붙이면 된다.
2026-11-02: --themes - 테마 소속(직접·부분)도 새 분기가 DART에 없을 때만 받는다(실적 축이 DART 분기 매출을 먼저 읽게 됨).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.db.data_store import get_db
from src.db.quarterly_financials import (ensure_schema, insert_quarter, migrate_legacy_rows,
                                          select_quarters, select_quarters_bulk)
from collectors import dart_client as dart
from collectors.dart_financials import REPORT_CODES, latest_quarters, quarterly_values

CORP_CACHE = ROOT / "data" / "dart_corp_codes.json"
UNIVERSE = ROOT / "data" / "kr_universe.json"
CALL_SLEEP = 0.12  # DART 분당 요청 제한 여유


def _log(msg: str) -> None:
    print(f"[dart-fin] {msg}", flush=True)


def collect_one(corp_code: str, today: date, years: int = 2, start_year: int | None = None, fallback: bool = True) -> dict:
    """start_year부터 거꾸로 years개 사업연도 보고서. fallback이면 5분기가 안 모일 때 한 해 더(재작년)."""
    start = start_year or today.year
    reports: dict = {}
    for year in range(start, start - years, -1):
        for code in REPORT_CODES:
            reports[(year, code)] = dart.fetch_key_accounts(corp_code, year, code)
            time.sleep(CALL_SLEEP)
    values = quarterly_values(reports)
    if fallback and len(latest_quarters(values)) < 5 and years < 3:
        year = start - 2
        for code in REPORT_CODES:
            reports[(year, code)] = dart.fetch_key_accounts(corp_code, year, code)
            time.sleep(CALL_SLEEP)
        values = quarterly_values(reports)
    return values


def watchlist_tickers() -> list[str]:
    """워치리스트 후보 + 내 워치리스트(KR). 표가 없으면 그 표만 건너뛴다.
    테마 소속(약 425종목)은 넣지 않는다 - 3개 연도면 종목당 약 24초라 Actions 제한(180분)을 넘고, 4분기 합 비교는 워치리스트 화면만 쓴다."""
    conn = get_db()
    out: set[str] = set()
    for sql in ("SELECT symbol FROM watchlist_candidates WHERE market = 'KR'",
                "SELECT symbol FROM my_watchlist WHERE market = 'KR'"):
        try:
            out.update(r[0] for r in conn.execute(sql).fetchall() if r[0])
        except Exception as e:  # noqa: BLE001
            _log(f"대상 조회 실패({type(e).__name__}) - 건너뜀: {sql[:50]}")
    conn.close()
    return sorted(out)


def theme_tickers() -> list[str]:
    """실적 축이 쓰는 한국 테마 소속(승인, 직접·부분 연관). 2026-11-02 추가 - 실적 축이 DART 분기 매출을 먼저 읽는다."""
    conn = get_db()
    try:
        rows = conn.execute("SELECT DISTINCT ticker FROM theme_members WHERE market = 'KR' AND approved = 1 "
                            "AND linkage IN ('direct', 'partial')").fetchall()
    except Exception as e:  # noqa: BLE001
        _log(f"테마 소속 조회 실패({type(e).__name__}) - 건너뜀")
        rows = []
    conn.close()
    return sorted({r[0] for r in rows if r[0]})


def target_quarter(today: date) -> tuple[int, int]:
    """지금 나올 차례인 분기 = 오늘 직전에 끝난 분기(11월이면 3분기)."""
    q = (today.month - 1) // 3
    return (today.year - 1, 4) if q == 0 else (today.year, q)


def incremental_plan(quarters: list[dict], target: tuple[int, int]) -> str:
    """테마 소속 한 종목을 어떻게 받을지: 'skip'(DART에 그 분기가 이미 있음) / 'one_year'(직전 4분기는 있어 그 분기 연도만) / 'full'.
    테마 소속은 약 300종목이라 매주 다 받으면 오래 걸린다(종목당 8회 호출 약 16초) - 새 분기가 나올 때만, 필요한 만큼만."""
    have = {(r["fiscal_year"], r["fiscal_quarter"]) for r in quarters if r.get("source") == "DART" and r.get("revenue") is not None}
    if target in have:
        return "skip"
    y, q = target
    prev = []
    for _ in range(4):
        y, q = (y, q - 1) if q > 1 else (y - 1, 4)
        prev.append((y, q))
    return "one_year" if all(k in have for k in prev) and target[1] != 4 else "full"


def fmt_eok(v) -> str:
    """원 -> 억원(표 확인용)."""
    return "-" if v is None else f"{v / 1e8:,.0f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", default=None, help="종목코드 몇 개만 (확인용)")
    ap.add_argument("--offset", type=int, default=0, help="유니버스 정렬 순서에서 이만큼 건너뛴다")
    ap.add_argument("--limit", type=int, default=None, help="offset부터 N개만")
    ap.add_argument("--watchlist", action="store_true",
                    help="유니버스 전체 대신 워치리스트 후보 + 내 워치리스트(KR)")
    ap.add_argument("--years", type=int, default=2, help="받을 사업연도 수(올해부터 거꾸로). 연속 8분기에는 3")
    ap.add_argument("--themes", action="store_true",
                    help="테마 소속(직접·부분)도 - 새 분기가 DART에 없는 종목만, 필요한 연도만(incremental_plan)")
    args = ap.parse_args()

    universe = {i["symbol"]: i for i in json.loads(UNIVERSE.read_text(encoding="utf-8"))["items"]}
    tickers = args.tickers or sorted(universe)
    if args.watchlist and not args.tickers:
        tickers = watchlist_tickers()
    if args.offset or args.limit:
        end = args.offset + args.limit if args.limit else None
        tickers = tickers[args.offset:end]

    corp = dart.load_corp_codes(CORP_CACHE)
    conn = get_db()
    ensure_schema(conn)
    today = date.today()
    # 테마 소속(워치리스트에 없는 것만): 새 분기가 DART에 아직 없으면 받는다 - 실적 축이 DART 분기 매출을 먼저 읽는다(2026-11-02)
    plan: dict[str, str] = {}
    if args.themes and not args.tickers:
        target = target_quarter(today)
        extra = [t for t in theme_tickers() if t not in set(tickers)]
        have = select_quarters_bulk(conn, extra, "KR")
        plan = {t: incremental_plan(have.get(t, []), target) for t in extra}
        skip = sum(1 for v in plan.values() if v == "skip")
        tickers = tickers + [t for t in extra if plan[t] != "skip"]
        _log(f"테마 소속(워치리스트 밖) {len(extra)}종목 - {target[0]}Q{target[1]}가 이미 있음 {skip}, "
             f"받을 것 {len(extra) - skip}(그 연도만 {sum(1 for v in plan.values() if v == 'one_year')})")
    _log(f"기업코드 매핑 {len(corp)}건 / 대상 {len(tickers)}종목")

    moved = migrate_legacy_rows(conn)   # 예전 테이블 값을 raw로 옮긴다(여러 번 돌려도 안전)
    if moved:
        _log(f"예전 테이블에서 {moved}행을 원본 테이블로 옮겼다")
    now = datetime.utcnow().isoformat()
    stats = {"ok": 0, "no_corp": 0, "no_data": 0, "lt5": 0, "error": 0, "ofs": 0}
    first_error = ""

    for n, t in enumerate(tickers, 1):
        cc = corp.get(t)
        if not cc:
            stats["no_corp"] += 1
            _log(f"  {t} {universe.get(t, {}).get('name', '')}: DART 기업코드 없음")
            continue
        try:
            if plan.get(t) == "one_year":
                values = collect_one(cc, today, 1, start_year=target_quarter(today)[0], fallback=False)
            else:
                values = collect_one(cc, today, args.years)
        except dart.DartKeyError:
            raise
        except Exception as e:  # noqa: BLE001 - 한 종목 실패로 전체를 멈추지 않는다
            stats["error"] += 1
            first_error = first_error or f"{type(e).__name__}: {str(e)[:300]}"
            _log(f"  {t}: 실패 {type(e).__name__}: {str(e)[:120]}")
            # 처음 5종목이 전부 실패하면 DART 쪽 문제(점검 등) - 나머지를 돌려도 같은 결과라 멈춘다
            if stats["ok"] == 0 and stats["error"] >= 5 and n == stats["error"] + stats["no_corp"]:
                _log(f"처음 {n}종목이 전부 실패 - DART 응답 문제로 보고 중단. 첫 오류: {first_error}")
                conn.close()
                return 1
            continue
        if not values:
            stats["no_data"] += 1
            continue
        for (y, q), v in values.items():
            insert_quarter(conn, t, "KR", y, q, v, "DART", "KRW", now)
        conn.commit()
        stats["ok"] += 1
        recent = latest_quarters(values)
        if len(recent) < 5:
            stats["lt5"] += 1
        if recent and recent[0][1].get("fs_div") == "OFS":
            stats["ofs"] += 1
        if n % 50 == 0:
            _log(f"  진행 {n}/{len(tickers)} {stats}")

    _log(f"완료 {stats} (lt5=최근 5분기 미만, ofs=최신 분기가 별도재무)")
    if stats["ok"] == 0 and stats["error"] > 0:
        # 전부 실패인데 성공으로 끝나면 아무도 모른다(2026-10-11 정기 실행이 그랬다) - 실패로 끝내 알림이 가게 한다
        _log(f"성공 0종목 - 실패로 끝낸다. 첫 오류: {first_error}")
        conn.close()
        return 1

    if args.tickers:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        for t in args.tickers:
            name = universe.get(t, {}).get("name", "")
            rows = select_quarters(conn, t, "KR")[:5]
            print(f"\n{t} {name}  (단위: 억원)")
            print(f"  {'분기':8s} {'매출':>12s} {'영업이익':>10s} {'순이익':>10s}  구분  산출")
            for r in rows:
                print(f"  {r['fiscal_year']}Q{r['fiscal_quarter']}   {fmt_eok(r['revenue']):>12s} "
                      f"{fmt_eok(r['operating_income']):>10s} {fmt_eok(r['net_income']):>10s}  "
                      f"{r['fs_div'] or '-':4s}  {'4분기 계산' if r['derived'] == 'annual_minus_9m' else '보고값'}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
