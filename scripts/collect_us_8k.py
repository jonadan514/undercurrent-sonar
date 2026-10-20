"""미국 8-K 주요 공시를 us_8k_filings에 쌓는다 (2026-10-21, 사용자 결정: 다음 작업 2번). 규칙은 src/collectors/us_8k.py.

대상: 워치리스트 후보 + 내 관심 + 관찰 노트 종목 + 승인된 테마 소속 기업(내부자 매수와 같은 목록).
SEC submissions(회사별 최근 공시 목록)의 items로 종류를 정하고, 보는 항목이 있으면 본문을 받아 항목 첫머리를 원문 그대로 잘라 둔다.
실적 발표(2.02)만 있는 8-K는 본문을 받지 않는다. 이력 표라 덮어쓰지 않는다(원칙 5) - 이미 받은 공시는 건너뛴다.

    python scripts/collect_us_8k.py --days 14
    python scripts/collect_us_8k.py --tickers MU NVDA --days 60   # 확인용(저장 안 함)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.collect_insider_trades import targets
from src.collectors import sec_client as sec
from src.collectors.us_8k import describe, html_text, recent_8k
from src.db.data_store import get_db

DDL = """
CREATE TABLE IF NOT EXISTS us_8k_filings (
  accession  TEXT PRIMARY KEY,
  symbol     TEXT NOT NULL,
  filed_on   TEXT NOT NULL,
  items      TEXT NOT NULL,      -- 보는 항목 번호, 쉼표 구분 (예: 1.01,5.02)
  detail     TEXT NOT NULL,      -- describe() JSON: 항목별 이름·주의 표시·원문 발췌
  warn       INTEGER NOT NULL,   -- 1 = 해지·손상·사임 등 나쁜 쪽일 수 있는 종류가 들어 있음(분류일 뿐 점수 아님)
  url        TEXT,
  fetched_at TEXT NOT NULL
)
"""


def _log(msg: str) -> None:
    print(f"[8k] {msg}", flush=True)


def collect(conn, tickers: list[str], since: str, save: bool) -> dict:
    s = sec.session()
    ciks = sec.ticker_ciks(s)
    have = {r[0] for r in conn.execute("SELECT accession FROM us_8k_filings").fetchall()} if save else set()
    stats = {"companies": 0, "no_cik": 0, "filings": 0, "fetched": 0, "warn": 0, "errors": 0}
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
        for f in recent_8k(sub, since):
            if f["accession"] in have:
                continue
            stats["filings"] += 1
            url = sec.doc_url(cik, f["accession"], f["doc"]) if f["doc"] else None
            text = None
            if url and f["items"] != ["2.02"]:
                try:
                    raw = sec.get(s, url, as_json=False)
                    text = html_text(raw) if raw else None
                    stats["fetched"] += 1
                except Exception as e:  # noqa: BLE001 - 본문을 못 받아도 항목 번호는 남긴다
                    stats["errors"] += 1
                    _log(f"  {t} {f['accession']}: 본문 실패 {type(e).__name__}")
            d = describe(f["items"], text)
            stats["warn"] += int(d["warn"])
            if not save:
                _log(f"  {t} {f['filed_on']} " + " / ".join(x["label"] + ("(!)" if x["warn"] else "") for x in d["items"]))
                for x in d["items"]:
                    if x["excerpt"]:
                        _log(f"      {x['item']}: {x['excerpt'][:200]}")
                continue
            conn.execute("INSERT OR IGNORE INTO us_8k_filings (accession, symbol, filed_on, items, detail, warn, url, fetched_at) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (f["accession"], t, f["filed_on"], ",".join(f["items"]), json.dumps(d, ensure_ascii=False),
                          int(d["warn"]), url, now))
        if save and n % 25 == 0:
            conn.commit()
            _log(f"  진행 {n}/{len(tickers)} {stats}")
    if save:
        conn.commit()
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14, help="공시일 기준 며칠 전까지")
    ap.add_argument("--tickers", nargs="*", default=None, help="몇 종목만 확인(저장 안 함)")
    args = ap.parse_args()

    since = (date.today() - timedelta(days=args.days)).isoformat()
    save = not args.tickers
    conn = get_db()
    if save:
        conn.execute(DDL)
        conn.commit()
    tickers = args.tickers or targets(conn, "US")
    _log(f"대상 {len(tickers)}종목, {since} 이후 8-K")
    stats = collect(conn, tickers, since, save)
    _log(f"완료 {stats}")
    conn.close()
    if save and len(tickers) >= 20 and stats["companies"] == 0:
        _log("회사 목록을 하나도 못 받음 - 실패로 끝낸다")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
