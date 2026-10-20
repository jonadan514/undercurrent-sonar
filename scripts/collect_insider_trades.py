"""내부자 장내 매수를 insider_trades에 쌓는다 (2026-10-21, 사용자 결정: 다음 작업 1번). 규칙은 src/collectors/insider_trades.py.

대상: 워치리스트 후보 + 내 관심 + 관찰 노트 종목 + 승인된 테마 소속 기업(테마마다 최근 승인 run).
이력 표라 덮어쓰지 않는다(원칙 5): (시장, 공시번호, 줄)이 키, 이미 받은 공시는 다시 받지 않는다.

미국: SEC submissions(회사별 최근 공시 목록)에서 기간 안의 Form 4만 골라 원본 XML을 읽는다.
      SEC는 User-Agent에 연락처 필수(SEC_USER_AGENT, Secrets), 초당 10회 한도 -> 호출 사이 0.15초.

    python scripts/collect_insider_trades.py --market US --days 14
    python scripts/collect_insider_trades.py --market US --tickers MU NVDA   # 확인용(저장 안 함)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.collectors.insider_trades import parse_form4, raw_xml_name
from src.db.data_store import get_db

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
SEC_SLEEP = 0.15

INSIDER_TRADES_DDL = """
CREATE TABLE IF NOT EXISTS insider_trades (
  market      TEXT NOT NULL,
  symbol      TEXT NOT NULL,
  filing_id   TEXT NOT NULL,     -- 미국 accession number / 한국 접수번호
  line        INTEGER NOT NULL,  -- 한 공시 안의 거래 순번
  filed_on    TEXT,              -- 공시일
  trade_date  TEXT,              -- 거래일
  owner       TEXT,
  role        TEXT,
  shares      REAL,
  price       REAL,
  value       REAL,              -- 주식 수 x 단가 (미국 달러 / 한국 원)
  owned_after REAL,
  direct      INTEGER,           -- 1 = 본인 명의
  plan        INTEGER,           -- 1 = 10b5-1 계획 매수(미국)
  source      TEXT NOT NULL,
  fetched_at  TEXT NOT NULL,
  PRIMARY KEY (market, filing_id, line)
)
"""


def _log(msg: str) -> None:
    print(f"[insider] {msg}", flush=True)


def targets(conn, market: str) -> list[str]:
    out: set[str] = set()
    for sql in ("SELECT symbol FROM watchlist_candidates WHERE market = ?",
                "SELECT symbol FROM my_watchlist WHERE market = ?",
                "SELECT DISTINCT ticker FROM observations WHERE kind = 'stock' AND market = ? AND ticker IS NOT NULL",
                "SELECT DISTINCT m.ticker FROM theme_members m WHERE m.market = ? AND m.approved = 1 AND m.run_id = "
                "(SELECT MAX(run_id) FROM theme_members t WHERE t.theme_id = m.theme_id AND t.market = m.market AND t.approved = 1)"):
        try:
            out.update(r[0] for r in conn.execute(sql, (market,)).fetchall() if r[0])
        except Exception as e:  # noqa: BLE001 - 표가 없으면 그 출처만 건너뛴다
            _log(f"대상 조회 실패({type(e).__name__}) - 건너뜀")
    return sorted(out)


# ── 미국 (SEC Form 4) ─────────────────────────────────────────────────────────

def _sec_session() -> requests.Session:
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua:
        raise SystemExit("SEC_USER_AGENT 환경변수가 없다 (GitHub Secrets)")
    s = requests.Session()
    s.headers.update({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
    return s


def _sec_get(s: requests.Session, url: str, as_json: bool = True):
    for attempt in range(4):
        try:
            r = s.get(url, timeout=60)
            if r.status_code == 404:
                return None
            if r.status_code in (403, 429) or r.status_code >= 500:
                time.sleep(2 ** (attempt + 1))
                continue
            r.raise_for_status()
            return r.json() if as_json else r.text
        except (requests.Timeout, requests.ConnectionError, ValueError):
            time.sleep(2 ** (attempt + 1))
        finally:
            time.sleep(SEC_SLEEP)
    raise RuntimeError(f"SEC 호출 실패 {url}")


def recent_form4(sub: dict, since: str) -> list[tuple[str, str, str]]:
    """submissions JSON -> [(accession, 공시일, 원본 XML 이름)] - 기간 안의 Form 4만(4/A 정정은 뺀다)."""
    rec = (sub.get("filings") or {}).get("recent") or {}
    out = []
    for form, acc, filed, doc in zip(rec.get("form", []), rec.get("accessionNumber", []),
                                     rec.get("filingDate", []), rec.get("primaryDocument", [])):
        if form == "4" and filed >= since and doc:
            out.append((acc, filed, raw_xml_name(doc)))
    return out


def collect_us(conn, tickers: list[str], since: str, save: bool) -> dict:
    s = _sec_session()
    ciks = {str(v["ticker"]).upper(): int(v["cik_str"]) for v in (_sec_get(s, SEC_TICKERS_URL) or {}).values()}
    have = set()
    if save:
        have = {r[0] for r in conn.execute("SELECT DISTINCT filing_id FROM insider_trades WHERE market = 'US'").fetchall()}
    stats = {"companies": 0, "no_cik": 0, "form4": 0, "buys": 0, "errors": 0}
    now = datetime.utcnow().isoformat()
    for n, t in enumerate(tickers, 1):
        cik = ciks.get(t.upper()) or ciks.get(t.upper().replace(".", "-"))
        if not cik:
            stats["no_cik"] += 1
            continue
        try:
            sub = _sec_get(s, SEC_SUBMISSIONS_URL.format(cik=cik)) or {}
        except Exception as e:  # noqa: BLE001 - 한 회사 실패로 전체를 멈추지 않는다
            stats["errors"] += 1
            _log(f"  {t}: 공시 목록 실패 {type(e).__name__}")
            continue
        stats["companies"] += 1
        for acc, filed, doc in recent_form4(sub, since):
            if acc in have:
                continue
            stats["form4"] += 1
            try:
                xml = _sec_get(s, SEC_DOC_URL.format(cik=cik, acc=acc.replace("-", ""), doc=doc), as_json=False)
                buys = parse_form4(xml) if xml else []
            except Exception as e:  # noqa: BLE001
                stats["errors"] += 1
                _log(f"  {t} {acc}: 원문 실패 {type(e).__name__}: {str(e)[:80]}")
                continue
            for b in buys:
                stats["buys"] += 1
                if not save:
                    _log(f"  {t} {b['trade_date']} {b['owner']} ({b['role']}) {b['shares']:,.0f}주 x ${b['price']} "
                         f"= ${b['value'] or 0:,.0f}{' [10b5-1]' if b['plan'] else ''}")
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO insider_trades (market, symbol, filing_id, line, filed_on, trade_date, owner, role, "
                    "shares, price, value, owned_after, direct, plan, source, fetched_at) "
                    "VALUES ('US', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SEC', ?)",
                    (t, acc, b["line"], filed, b["trade_date"], b["owner"], b["role"], b["shares"], b["price"], b["value"],
                     b["owned_after"], int(b["direct"]), int(b["plan"]), now))
        if save and n % 25 == 0:
            conn.commit()
            _log(f"  진행 {n}/{len(tickers)} {stats}")
    if save:
        conn.commit()
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["US", "KR"], required=True)
    ap.add_argument("--days", type=int, default=14, help="공시일 기준 며칠 전까지")
    ap.add_argument("--tickers", nargs="*", default=None, help="몇 종목만 확인(저장 안 함)")
    args = ap.parse_args()

    since = (date.today() - timedelta(days=args.days)).isoformat()
    save = not args.tickers
    conn = get_db()
    if save:
        conn.execute(INSIDER_TRADES_DDL)
        conn.commit()
    tickers = args.tickers or targets(conn, args.market)
    _log(f"{args.market} 대상 {len(tickers)}종목, {since} 이후 공시")
    if args.market == "US":
        stats = collect_us(conn, tickers, since, save)
    else:
        _log("KR 수집은 아직 준비 중 - 건너뜀")
        conn.close()
        return 0
    _log(f"완료 {stats}")
    conn.close()
    if save and len(tickers) >= 20 and stats.get("companies", 0) == 0:
        _log("회사 목록을 하나도 못 받음 - 실패로 끝낸다")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
