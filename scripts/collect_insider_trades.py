"""내부자 장내 매수를 insider_trades에 쌓는다 (2026-10-21, 사용자 결정: 다음 작업 1번). 규칙은 src/collectors/insider_trades.py.

대상: 워치리스트 후보 + 내 관심 + 관찰 노트 종목 + 승인된 테마 소속 기업(테마마다 최근 승인 run).
이력 표라 덮어쓰지 않는다(원칙 5): (시장, 공시번호, 줄)이 키, 이미 받은 공시는 다시 받지 않는다.

미국: SEC submissions(회사별 최근 공시 목록)에서 기간 안의 Form 4만 골라 원본 XML을 읽는다.
      SEC 호출 규칙(연락처 User-Agent·초당 한도)은 src/collectors/sec_client.py.
한국: DART 지분공시 목록(pblntf_ty=D)에서 "임원ㆍ주요주주특정증권등소유상황보고서"(정정 제외)를 골라 웹 뷰어 원문 표를 읽는다.
      대상은 위 목록 + 한국 유니버스(시총 3000억+) - 새 종목 아이디어용. 웹 뷰어는 조회 사이 0.5초.
읽은 공시는 insider_filings_seen에 남겨 매수가 없던 공시도 다시 받지 않는다.

    python scripts/collect_insider_trades.py --market US --days 14
    python scripts/collect_insider_trades.py --market US --tickers MU NVDA   # 확인용(저장 안 함)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from collectors import dart_client as dart
from src.collectors import sec_client as sec
from src.collectors.insider_trades import clean_role, is_open_market_buy, parse_form4, parse_kr_ownership, raw_xml_name
from src.db.data_store import get_db

KR_UNIVERSE = ROOT / "data" / "kr_universe.json"
KR_REPORT = "임원ㆍ주요주주특정증권등소유상황보고서"
VIEWER_SLEEP = 0.5


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
SEEN_DDL = """
CREATE TABLE IF NOT EXISTS insider_filings_seen (
  market     TEXT NOT NULL,
  filing_id  TEXT NOT NULL,
  buys       INTEGER NOT NULL,   -- 그 공시에서 찾은 장내 매수 줄 수
  checked_at TEXT NOT NULL,
  PRIMARY KEY (market, filing_id)
)
"""


def _insert(conn, market: str, symbol: str, filing_id: str, filed: str, b: dict, source: str, now: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO insider_trades (market, symbol, filing_id, line, filed_on, trade_date, owner, role, "
        "shares, price, value, owned_after, direct, plan, source, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (market, symbol, filing_id, b["line"], filed, b["trade_date"], b["owner"], b["role"], b["shares"], b["price"],
         b["value"], b["owned_after"], int(b["direct"]), int(b["plan"]), source, now))


def _seen(conn, market: str) -> set[str]:
    return {r[0] for r in conn.execute("SELECT filing_id FROM insider_filings_seen WHERE market = ?", (market,)).fetchall()}


def _mark(conn, market: str, filing_id: str, buys: int, now: str) -> None:
    conn.execute("INSERT OR IGNORE INTO insider_filings_seen (market, filing_id, buys, checked_at) VALUES (?, ?, ?, ?)",
                 (market, filing_id, buys, now))


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
    s = sec.session()
    ciks = sec.ticker_ciks(s)
    have = _seen(conn, "US") if save else set()
    stats = {"companies": 0, "no_cik": 0, "form4": 0, "buys": 0, "errors": 0}
    now = datetime.utcnow().isoformat()
    for n, t in enumerate(tickers, 1):
        cik = sec.cik_for(ciks, t)
        if not cik:
            stats["no_cik"] += 1
            continue
        try:
            sub = sec.get(s, sec.SEC_SUBMISSIONS_URL.format(cik=cik)) or {}
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
                xml = sec.get(s, sec.doc_url(cik, acc, doc), as_json=False)
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
                _insert(conn, "US", t, acc, filed, b, "SEC", now)
            if save:
                _mark(conn, "US", acc, len(buys), now)
        if save and n % 25 == 0:
            conn.commit()
            _log(f"  진행 {n}/{len(tickers)} {stats}")
    if save:
        conn.commit()
    return stats


# ── 한국 (DART 임원ㆍ주요주주 소유상황 보고) ───────────────────────────────────

def collect_kr(conn, tickers: list[str], days: int, save: bool) -> dict:
    today = date.today()
    targets_set = set(tickers)
    if save:   # 정기 실행은 유니버스(시총 3000억+)도 - 새 종목 아이디어용
        try:
            targets_set |= {i["symbol"] for i in json.loads(KR_UNIVERSE.read_text(encoding="utf-8")).get("items", [])}
        except Exception:  # noqa: BLE001
            _log("유니버스 파일 없음 - 관심 종목만")
    # 지분공시는 2주에 1,100건 안팎 - 목록 함수가 4,000건(40쪽)에서 멈추므로 긴 기간은 14일씩 나눠 받는다
    # (2026-10-21 60일 채우기에서 4,000건에서 잘린 것을 보고 고침).
    items: list[dict] = []
    end = today
    while end > today - timedelta(days=days):
        start = max(end - timedelta(days=13), today - timedelta(days=days))
        items += dart.list_disclosures(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), pblntf_ty="D")
        end = start - timedelta(days=1)
    reports = [i for i in items if KR_REPORT in i.get("report_nm", "") and "정정" not in i["report_nm"]
               and i.get("stock_code") in targets_set]
    have = _seen(conn, "KR") if save else set()
    stats = {"reports": len(reports), "new": 0, "buys": 0, "no_table": 0}
    _log(f"지분공시 {len(items)}건 중 대상 임원·주요주주 보고 {len(reports)}건")
    now = datetime.utcnow().isoformat()
    ele_cache: dict[str, dict[str, dict]] = {}

    def who(i: dict) -> tuple[str, str] | None:
        """보고자·직함은 정형 API(elestock)에서 - 웹 뷰어 글자는 일부가 '?'로 깨져 온다. 못 받으면 None."""
        cc = i.get("corp_code")
        if not cc:
            return None
        if cc not in ele_cache:
            try:
                ele_cache[cc] = {e.get("rcept_no"): e for e in dart.fetch_elestock(cc)}
            except Exception as e:  # noqa: BLE001
                _log(f"  {i['corp_name']}: 소유보고 목록 실패 {type(e).__name__}")
                ele_cache[cc] = {}
        e = ele_cache[cc].get(i["rcept_no"])
        if not e:
            return None
        parts = [p for p in (clean_role(e.get("isu_exctv_ofcps")), clean_role(e.get("isu_main_shrholdr"))) if p]
        return (e.get("repror") or i.get("flr_nm") or "-").strip(), " · ".join(parts) or "-"

    for i in reports:
        if i["rcept_no"] in have:
            continue
        stats["new"] += 1
        rows = dart.viewer_rows(i["rcept_no"])
        time.sleep(VIEWER_SLEEP)
        if not rows:
            stats["no_table"] += 1
            if not save:
                _log(f"  {i['corp_name']} {i['rcept_no']} 웹 뷰어 원문 없음")
            continue
        filed = f"{i['rcept_dt'][:4]}-{i['rcept_dt'][4:6]}-{i['rcept_dt'][6:8]}"
        buys = parse_kr_ownership(rows)
        # 깨진 글자라 장내인지 못 가린 '매수' 줄 - 빠뜨린 것이 있는지 보이게 남긴다(넣지는 않는다)
        odd = [r.split("|")[0].strip() for r in rows if "매수(+)" in r.split("|")[0] and "?" in r.split("|")[0]
               and not is_open_market_buy(r.split("|")[0]) and "?옣?쇅" not in r.split("|")[0]]
        if odd:
            stats["unknown_reason"] = stats.get("unknown_reason", 0) + len(odd)
            _log(f"  {i['corp_name']} {i['rcept_no']} 사유 판독 불가 {len(odd)}줄: {odd[:3]}")
        if buys:
            w = who(i)
            if not save:
                _log(f"  {i['corp_name']} 정형 API 보고자: {w if w else '못 찾음(뷰어 표 값 사용)'}")
            for b in buys:
                b["owner"], b["role"] = w if w else (i.get("flr_nm") or b["owner"], b["role"])
        if not save and not buys:   # 확인용: 변동 내역 줄 모양을 본다
            _log(f"  {i['corp_name']} {i['rcept_no']} 매수 없음 - 변동 줄: "
                 + " || ".join(r[:120] for r in rows if "(+)" in r or "(-)" in r)[:600])
        for b in buys:
            stats["buys"] += 1
            if not save:
                _log(f"  {i['corp_name']} {b['trade_date']} {b['owner']} ({b['role']}) {b['shares']:,.0f}주 x {b['price']}원 [{b.get('reason')}]")
                continue
            _insert(conn, "KR", i["stock_code"], i["rcept_no"], filed, b, "DART", now)
        if save:
            _mark(conn, "KR", i["rcept_no"], len(buys), now)
            if stats["new"] % 25 == 0:
                conn.commit()
                _log(f"  진행 {stats}")
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
        conn.execute(SEEN_DDL)
        conn.commit()
    tickers = args.tickers or targets(conn, args.market)
    _log(f"{args.market} 대상 {len(tickers)}종목, {since} 이후 공시")
    if args.market == "US":
        stats = collect_us(conn, tickers, since, save)
    else:
        stats = collect_kr(conn, tickers, args.days, save)
    _log(f"완료 {stats}")
    conn.close()
    if save and args.market == "US" and len(tickers) >= 20 and stats.get("companies", 0) == 0:
        _log("회사 목록을 하나도 못 받음 - 실패로 끝낸다")
        return 1
    if save and args.market == "KR" and stats["new"] >= 10 and stats["no_table"] == stats["new"]:
        _log("웹 뷰어 원문을 하나도 못 읽음 - 실패로 끝낸다")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
