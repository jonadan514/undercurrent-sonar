"""13F 보유 수집 (2026-10-25, 사용자 선택 운용사 15곳 - config/institutions.yaml). 규칙은 src/collectors/sec_13f.py.

매일 운용사마다 SEC 제출 목록을 보고, 아직 안 받은 13F-HR(/A)만 받는다(분기마다 2월·5월·8월·11월 중순에 몰린다).
  - inst_13f_filings / inst_13f_rows: 신고서 그대로(신고마다 종목별 합계) - 이력이라 덮어쓰지 않는다(INSERT OR IGNORE, 원칙 5).
  - inst_13f_positions: 분기별 보유 + 직전 분기 비교(새로·늘림·줄임·전량 매도) - 위 두 표에서 다시 만드는 파생 표라 분기마다 바꿔 쓴다.
  - cusip_map: CUSIP -> 티커(OpenFIGI), 한 번 찾은 건 다시 안 묻는다.

    python scripts/collect_13f.py [--quarters 5] [--managers berkshire baupost]
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.collectors.sec_13f import (combine_period, diff_positions, fetch_filing, is_debt, list_13f_filings, map_cusips,  # noqa: E402
                                    merge_renamed, name_match, norm_issuer, normalize_rows, quarter_label, submissions,
                                    valid_ticker, value_scale, with_weights)
from src.collectors.sec_client import SEC_TICKERS_URL, get, session  # noqa: E402
from src.db.data_store import get_db  # noqa: E402

DDL = [
    """CREATE TABLE IF NOT EXISTS inst_13f_filings (
      accession TEXT PRIMARY KEY, manager_id TEXT NOT NULL, cik INTEGER NOT NULL, form TEXT NOT NULL,
      period TEXT NOT NULL, filed_on TEXT NOT NULL, amendment_type TEXT, entries INTEGER, value_total REAL, fetched_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS inst_13f_rows (
      accession TEXT NOT NULL, cusip TEXT NOT NULL, put_call TEXT NOT NULL, issuer TEXT, title TEXT, shares REAL, value REAL,
      PRIMARY KEY (accession, cusip, put_call))""",
    """CREATE TABLE IF NOT EXISTS cusip_map (
      cusip TEXT PRIMARY KEY, ticker TEXT, name TEXT, exch TEXT, security_type TEXT, source TEXT, mapped_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS inst_13f_positions (
      manager_id TEXT NOT NULL, period TEXT NOT NULL, cusip TEXT NOT NULL, put_call TEXT NOT NULL,
      ticker TEXT, issuer TEXT, title TEXT, shares REAL, value REAL, weight REAL,
      status TEXT, prev_shares REAL, share_chg REAL, filed_on TEXT, computed_at TEXT NOT NULL, prev_value REAL,
      PRIMARY KEY (manager_id, period, cusip, put_call))""",
    "CREATE INDEX IF NOT EXISTS idx_13f_pos_ticker ON inst_13f_positions(ticker)",
]
LATE_COLUMNS = [("inst_13f_positions", "prev_value", "REAL")]   # 직전 분기 평가액 - 전량 매도를 크기 순으로(2026-10-25)


def _log(msg: str) -> None:
    print(f"[13f] {msg}", flush=True)


def cutoff_period(quarters: int, today: date) -> str:
    """최근 quarters개 분기 말의 가장 이른 날짜. 비교에 직전 분기가 필요해 하나 더 받는다."""
    q_end_month = ((today.month - 1) // 3) * 3     # 지난 분기 말 월(0이면 작년 12월)
    y, m = (today.year, q_end_month) if q_end_month else (today.year - 1, 12)
    for _ in range(quarters):
        m -= 3
        if m <= 0:
            m += 12
            y -= 1
    return f"{y}-{m:02d}-01"


def load_rows(conn, accession: str) -> dict:
    rows = conn.execute("SELECT cusip, put_call, issuer, title, shares, value FROM inst_13f_rows WHERE accession = ?", (accession,)).fetchall()
    return {(r[0], r[1]): {"cusip": r[0], "put_call": r[1], "issuer": r[2], "title": r[3], "shares": float(r[4] or 0), "value": float(r[5] or 0)}
            for r in rows}


def rebuild_positions(conn, manager_id: str, now: str) -> list[str]:
    """그 운용사의 받은 신고 전부로 분기별 보유·비교를 다시 만든다. -> 바뀐 분기 목록."""
    fl = conn.execute("SELECT accession, form, period, filed_on, amendment_type FROM inst_13f_filings WHERE manager_id = ? ORDER BY period",
                      (manager_id,)).fetchall()
    by_period: dict[str, list[dict]] = {}
    for acc, form, period, filed, amend in fl:
        raw = load_rows(conn, acc)
        if value_scale(raw) != 1:
            _log(f"{manager_id} {quarter_label(period)} {acc}: 가치가 천 달러 단위로 보여 1000을 곱함")
        # 원본 줄은 그대로 두고 비교할 때만 단위·채권 구분을 맞춘다(원칙 5)
        by_period.setdefault(period, []).append({"form": form, "filed": filed, "amendment_type": amend, "rows": normalize_rows(raw)})
    periods = sorted(by_period)
    prev = None
    prev_period = None
    for p in periods:
        cur = combine_period(by_period[p])
        # 직전 분기가 바로 앞 분기일 때만 비교(빠진 분기를 건너뛰면 '새로'가 부풀려진다)
        consecutive = prev_period is not None and _quarter_gap(prev_period, p) == 1
        rows = with_weights(merge_renamed(diff_positions(prev if consecutive else None, cur)))
        filed = max(f["filed"] for f in by_period[p])
        conn.execute("DELETE FROM inst_13f_positions WHERE manager_id = ? AND period = ?", (manager_id, p))
        for i in range(0, len(rows), 100):
            chunk = rows[i:i + 100]
            conn.execute(
                "INSERT INTO inst_13f_positions (manager_id, period, cusip, put_call, ticker, issuer, title, shares, value, weight, status, "
                "prev_shares, share_chg, filed_on, computed_at, prev_value) VALUES "
                + ", ".join(["(?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"] * len(chunk)),
                tuple(v for r in chunk for v in (manager_id, p, r["cusip"], r["put_call"], r["issuer"], r["title"], r["shares"], r["value"],
                                                 r["weight"], r["status"], r["prev_shares"], r["share_chg"], filed, now, r.get("prev_value"))))
        prev, prev_period = cur, p
    return periods


def _quarter_gap(a: str, b: str) -> int:
    ya, ma = int(a[:4]), int(a[5:7])
    yb, mb = int(b[:4]), int(b[5:7])
    return (yb * 12 + mb - (ya * 12 + ma)) // 3


def apply_tickers(conn) -> None:
    conn.execute("UPDATE inst_13f_positions SET ticker = (SELECT ticker FROM cusip_map m WHERE m.cusip = inst_13f_positions.cusip) "
                 "WHERE ticker IS NULL")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarters", type=int, default=5, help="최근 몇 분기(비교용으로 하나 더)")
    ap.add_argument("--managers", nargs="*", default=None)
    ap.add_argument("--rebuild", action="store_true", help="새 신고가 없어도 받은 신고로 분기 보유·비교를 다시 계산")
    ap.add_argument("--remap", action="store_true", help="티커를 못 찾았던 CUSIP도 OpenFIGI에 다시 묻기")
    args = ap.parse_args()

    managers = yaml.safe_load(open(ROOT / "config" / "institutions.yaml", encoding="utf-8"))["managers"]
    if args.managers:
        managers = [m for m in managers if m["id"] in args.managers]
    since = cutoff_period(args.quarters, date.today())
    conn = get_db()
    for d in DDL:
        conn.execute(d)
    for table, col, typ in LATE_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        except Exception:  # noqa: BLE001 - 이미 있음
            pass
    seen = {r[0] for r in conn.execute("SELECT accession FROM inst_13f_filings").fetchall()}
    s = session()
    now = datetime.utcnow().isoformat(timespec="seconds")
    new_filings = 0
    changed: list[str] = []
    for m in managers:
        sub = submissions(s, int(m["cik"]))
        fl = [f for f in list_13f_filings(sub) if f["period"] >= since]
        todo = [f for f in fl if f["accession"] not in seen]
        for f in todo:
            got = fetch_filing(s, int(m["cik"]), f["accession"])
            if got is None:
                _log(f"{m['id']} {f['accession']} 정보표를 못 찾음 - 다음 실행에 다시")
                continue
            conn.execute("INSERT OR IGNORE INTO inst_13f_filings (accession, manager_id, cik, form, period, filed_on, amendment_type, entries, "
                         "value_total, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (f["accession"], m["id"], int(m["cik"]), f["form"], f["period"], f["filed"], got["amendment_type"],
                          got["entries"], got["value_total"], now))
            rows = list(got["rows"].values())
            for i in range(0, len(rows), 100):
                chunk = rows[i:i + 100]
                conn.execute("INSERT OR IGNORE INTO inst_13f_rows (accession, cusip, put_call, issuer, title, shares, value) VALUES "
                             + ", ".join(["(?, ?, ?, ?, ?, ?, ?)"] * len(chunk)),
                             tuple(v for r in chunk for v in (f["accession"], r["cusip"], r["put_call"], r["issuer"], r["title"], r["shares"], r["value"])))
            new_filings += 1
            _log(f"{m['id']} {quarter_label(f['period'])} {f['form']}{' ' + got['amendment_type'] if got['amendment_type'] else ''} "
                 f"{f['filed']} 종목 {len(rows)}줄 (신고 합계 {got['entries']}줄)")
        if todo or args.rebuild:
            periods = rebuild_positions(conn, m["id"], now)
            changed.append(m["id"])
            conn.commit()
            _log(f"{m['id']}: 분기 {', '.join(quarter_label(p) for p in periods)} 다시 계산")
        else:
            latest = max((f["period"] for f in fl), default=None)
            _log(f"{m['id']}: 새 신고 없음 (최근 {quarter_label(latest) if latest else '-'})")

    # CUSIP -> 티커: 아직 안 물어본 것(--remap이면 못 찾았던 것도)을 OpenFIGI에, 그래도 없으면 SEC 회사 목록 이름 맞추기
    known = {r[0]: r[1] for r in conn.execute("SELECT cusip, ticker FROM cusip_map").fetchall()}
    if args.remap:   # 모양이 이상한 티커(채권·해외 상장)도 다시 - 2026-10-25 첫 실행에서 섞였다
        bad = [c for c, t in known.items() if t is not None and not valid_ticker(t)]
        for c in bad:
            known[c] = None
            conn.execute("UPDATE cusip_map SET ticker = NULL WHERE cusip = ?", (c,))
        if bad:
            conn.execute("UPDATE inst_13f_positions SET ticker = NULL WHERE cusip IN (" + ",".join("?" * len(bad)) + ")", tuple(bad))
            _log(f"모양이 이상한 티커 {len(bad)}개 지우고 다시 찾기")
    cur = {r[0]: r[1] for r in conn.execute("SELECT DISTINCT cusip, issuer FROM inst_13f_positions WHERE put_call != 'DEBT'").fetchall()}
    need = sorted(c for c in cur if c not in known or (args.remap and known[c] is None))
    if need:
        _log(f"CUSIP {len(need)}개 티커 찾기(OpenFIGI)")
        res = map_cusips(need, os.environ.get("OPENFIGI_API_KEY") or None, log=_log)
        for c, d in res.items():
            conn.execute("INSERT OR REPLACE INTO cusip_map (cusip, ticker, name, exch, security_type, source, mapped_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (c, d["ticker"] if d else None, d["name"] if d else None, d["exch"] if d else None,
                          d["security_type"] if d else None, "openfigi", now))
        _log(f"찾음 {sum(1 for d in res.values() if d and d['ticker'])} / 없음 {sum(1 for d in res.values() if not d or not d['ticker'])} / "
             f"다음에 다시 {len(need) - len(res)}")
    mapped = {r[0] for r in conn.execute("SELECT cusip FROM cusip_map WHERE ticker IS NOT NULL").fetchall()}
    missing = {c: n for c, n in cur.items() if not is_debt(c) and c not in mapped}
    if missing:
        titles: dict[str, set] = {}
        for v in (get(s, SEC_TICKERS_URL) or {}).values():
            titles.setdefault(norm_issuer(v.get("title")), set()).add(str(v["ticker"]).upper().replace("-", "."))
        unique = {k: next(iter(t)) for k, t in titles.items() if k and len(t) == 1}   # 이름이 겹치는 회사(종류주 등)는 맞추지 않는다
        hits = name_match(missing, unique)
        for c, t in hits.items():
            conn.execute("INSERT OR REPLACE INTO cusip_map (cusip, ticker, name, exch, security_type, source, mapped_at) VALUES (?, ?, ?, NULL, NULL, ?, ?)",
                         (c, t, missing[c], "sec_name", now))
        _log(f"OpenFIGI로 못 찾은 주식 {len(missing)}개 중 SEC 회사명으로 {len(hits)}개 맞춤")
    apply_tickers(conn)
    conn.commit()

    # 요약 로그 - 운용사별 최근 분기 새로·전량 매도 상위(평가액 순)
    for m in managers:
        row = conn.execute("SELECT MAX(period) FROM inst_13f_positions WHERE manager_id = ?", (m["id"],)).fetchone()
        p = row[0] if row else None
        if not p:
            continue
        cnt = dict(conn.execute("SELECT COALESCE(status, '-'), COUNT(*) FROM inst_13f_positions WHERE manager_id = ? AND period = ? "
                                "AND put_call = '' GROUP BY status", (m["id"], p)).fetchall())
        new = conn.execute("SELECT COALESCE(ticker, issuer), value FROM inst_13f_positions WHERE manager_id = ? AND period = ? AND status = 'new' "
                           "AND put_call = '' ORDER BY value DESC LIMIT 5", (m["id"], p)).fetchall()
        sold = conn.execute("SELECT COALESCE(ticker, issuer) FROM inst_13f_positions WHERE manager_id = ? AND period = ? AND status = 'sold' "
                            "AND put_call = '' ORDER BY prev_value DESC LIMIT 5", (m["id"], p)).fetchall()
        _log(f"{m['id']} {quarter_label(p)}: {cnt} · 새로 {[f'{t} ${v / 1e6:,.0f}M' for t, v in new]} · 전량 매도 {[t for (t,) in sold]}")
    conn.close()
    _log(f"완료 - 새 신고 {new_filings}건, 다시 계산 {len(changed)}곳")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
