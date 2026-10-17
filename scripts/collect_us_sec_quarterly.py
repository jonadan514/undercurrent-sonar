"""미국 워치리스트 종목 분기 재무를 SEC EDGAR(companyfacts)에서 받아 quarterly_financials_raw에 쌓는다 (2026-10-17).

yfinance 분기는 5개뿐이라 최근 4개 분기 합 비교(company_growth.ttm_revenue_yoy, 연속 8분기)를 못 한다 -
SEC 공시로 2023년 이후 분기를 채운다. 계산 규칙은 src/collectors/sec_financials.py.

SEC는 User-Agent에 연락처를 요구한다 -> 환경변수 SEC_USER_AGENT(GitHub Secrets, 저장소·로그에 남기지 않는다).
요청 한도 초당 10회 -> 호출 사이 0.15초.

같은 표의 yfinance 행과는 source가 달라 따로 쌓이고, 분기마다 늦게 수집된 값이 쓰인다(select_quarters).
매주 같은 값이 쌓이지 않게 처음 보는 분기·값이 바뀐 분기만 저장한다(collect_us_quarterly_financials와 같은 규칙).

    python scripts/collect_us_sec_quarterly.py                 # 미국 워치리스트 후보 + 내 워치리스트
    python scripts/collect_us_sec_quarterly.py --tickers AAPL MU   # 몇 종목 + 표 출력
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.collectors.sec_financials import quarterly_values
from src.db.data_store import get_db
from src.db.quarterly_financials import ensure_schema, insert_quarter, select_quarters

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
CALL_SLEEP = 0.15
SOURCE = "SEC"
VALUE_KEYS = ("revenue", "operating_income", "net_income")


def _log(msg: str) -> None:
    print(f"[sec-fin] {msg}", flush=True)


def _session() -> requests.Session:
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua:
        raise SystemExit("SEC_USER_AGENT 환경변수가 없다 (GitHub Secrets에 'U-Sonar 연락처이메일' 형식으로 등록)")
    s = requests.Session()
    s.headers.update({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
    return s


def _get_json(s: requests.Session, url: str) -> dict | None:
    for attempt in range(4):
        try:
            r = s.get(url, timeout=60)
            if r.status_code == 404:
                return None
            if r.status_code in (403, 429) or r.status_code >= 500:
                time.sleep(2 ** (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except (requests.Timeout, requests.ConnectionError, ValueError):
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"SEC 호출 실패 {url}")


def cik_map(s: requests.Session) -> dict[str, int]:
    data = _get_json(s, TICKERS_URL) or {}
    return {str(v["ticker"]).upper(): int(v["cik_str"]) for v in data.values()}


def watchlist_tickers(conn) -> list[str]:
    out: set[str] = set()
    for sql in ("SELECT symbol FROM watchlist_candidates WHERE market = 'US'",
                "SELECT symbol FROM my_watchlist WHERE market = 'US'"):
        try:
            out.update(r[0] for r in conn.execute(sql).fetchall() if r[0])
        except Exception as e:  # noqa: BLE001
            _log(f"대상 조회 실패({type(e).__name__}) - 건너뜀")
    return sorted(out)


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= max(1.0, abs(float(b)) * 1e-9)


def latest_sec_values(conn) -> dict[str, dict[tuple[int, int], tuple]]:
    rows = conn.execute(
        "SELECT ticker, fiscal_year, fiscal_quarter, revenue, operating_income, net_income "
        "FROM quarterly_financials_raw WHERE market = 'US' AND source = ? ORDER BY collected_on", (SOURCE,)
    ).fetchall()
    out: dict[str, dict[tuple[int, int], tuple]] = {}
    for t, y, q, rev, op, net in rows:
        out.setdefault(t, {})[(int(y), int(q))] = (rev, op, net)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", default=None, help="종목코드 몇 개만 (확인용, 표 출력)")
    args = ap.parse_args()

    s = _session()
    conn = get_db()
    ensure_schema(conn)
    tickers = args.tickers or watchlist_tickers(conn)
    ciks = cik_map(s)
    _log(f"SEC 기업 매핑 {len(ciks)}건 / 대상 {len(tickers)}종목")
    latest = latest_sec_values(conn)
    now = datetime.utcnow().isoformat()
    stats = {"ok": 0, "no_cik": 0, "no_data": 0, "error": 0, "lt8": 0, "unchanged": 0}
    saved = 0

    for n, t in enumerate(tickers, 1):
        cik = ciks.get(t.upper()) or ciks.get(t.upper().replace(".", "-"))
        if not cik:
            stats["no_cik"] += 1
            _log(f"  {t}: SEC 기업번호 없음")
            continue
        try:
            facts = _get_json(s, FACTS_URL.format(cik=cik))
        except Exception as e:  # noqa: BLE001 - 한 종목 실패로 전체를 멈추지 않는다
            stats["error"] += 1
            _log(f"  {t}: 실패 {type(e).__name__}: {str(e)[:120]}")
            continue
        finally:
            time.sleep(CALL_SLEEP)
        values = quarterly_values(facts or {})
        if not values:
            stats["no_data"] += 1
            _log(f"  {t}: 매출 분기 없음")
            continue
        prev = latest.get(t, {})
        to_save = {k: v for k, v in values.items()
                   if k not in prev or not all(_same(p, v.get(f)) for p, f in zip(prev[k], VALUE_KEYS))}
        for (y, q), v in to_save.items():
            insert_quarter(conn, t, "US", y, q, v, SOURCE, "USD", now)
        if to_save:
            conn.commit()
            saved += len(to_save)
        else:
            stats["unchanged"] += 1
        stats["ok"] += 1
        if len(values) < 8:
            stats["lt8"] += 1
        if n % 50 == 0:
            _log(f"  진행 {n}/{len(tickers)} {stats}")

    _log(f"완료 {stats} (lt8=2023년 이후 분기 8개 미만) / 저장 {saved}행")

    if args.tickers:
        for t in args.tickers:
            rows = [r for r in select_quarters(conn, t, "US")][:10]
            print(f"\n{t}  (단위: 백만 달러, 분기마다 늦게 수집된 출처)")
            for r in rows:
                def fmt(v):
                    return "-" if v is None else f"{v / 1e6:,.0f}"
                print(f"  {r['fiscal_year']}Q{r['fiscal_quarter']}  {fmt(r['revenue']):>10} {fmt(r['operating_income']):>10} "
                      f"{fmt(r['net_income']):>10}  {r.get('source')} {r.get('derived') or ''}")
    conn.close()
    if len(tickers) >= 20 and stats["ok"] == 0:
        _log("성공 0종목 - 실패로 끝낸다")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
