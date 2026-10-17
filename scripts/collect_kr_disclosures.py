"""한국 공시 알림 - 공급계약·잠정실적·결산실적 공시예고를 kr_disclosures에 쌓는다 (2026-10-17, 사용자 결정).

DART 거래소공시 목록에서 상장사 공시 중 세 종류만 골라 원문 표를 읽는다(규칙은 src/collectors/kr_disclosures.py).
전체 상장사를 받는다 - 주간 브리핑에서 유니버스(시총 3000억+)·관심 종목으로 거른다(새 종목 아이디어용).
이력 표라 덮어쓰지 않는다(원칙 5): 접수번호(rcept_no)가 키, 이미 있으면 원문을 다시 받지 않는다.

--notify면 새로 들어온 공시 중 내 관심·관찰 노트·워치리스트 후보 종목만 텔레그램으로 바로 알린다(없으면 안 보낸다).

    python scripts/collect_kr_disclosures.py --days 3 --notify     # 정기(매일)
    python scripts/collect_kr_disclosures.py --days 30             # 처음 채우기(알림 없음)
    python scripts/collect_kr_disclosures.py --probe 20261014 20261016   # 공시 종류·원문 표 확인(저장 안 함)
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from collectors import dart_client as dart
from src.collectors.kr_disclosures import DART_VIEW, PARSERS, classify, summary
from src.db.data_store import get_db

KST = timezone(timedelta(hours=9))
DOC_SLEEP = 0.2
KR_DISCLOSURES_DDL = """
CREATE TABLE IF NOT EXISTS kr_disclosures (
  rcept_no    TEXT PRIMARY KEY,
  rcept_dt    TEXT NOT NULL,      -- 접수일 'YYYY-MM-DD'
  stock_code  TEXT NOT NULL,
  corp_name   TEXT,
  corp_cls    TEXT,               -- Y 코스피 / K 코스닥
  kind        TEXT NOT NULL,      -- contract | prelim | notice
  report_nm   TEXT,
  payload     TEXT NOT NULL,      -- 파싱 결과 JSON (못 읽은 칸은 null)
  fetched_at  TEXT NOT NULL
)
"""
TAG_KO = {"my": "내 관심", "note": "노트", "cand": "워치"}


def _log(msg: str) -> None:
    print(f"[kr-disc] {msg}", flush=True)


def probe(bgn: str, end: str) -> int:
    items = dart.list_disclosures(bgn, end)
    print(f"공시 {len(items)}건")
    for n, c in Counter(i["report_nm"].strip() for i in items).most_common(40):
        print(f"  {c:4d} {n}")
    for kind in PARSERS:
        hits = [i for i in items if classify(i["report_nm"]) == kind and i.get("stock_code")][:3]
        for h in hits:
            rows = dart.document_rows(h["rcept_no"])
            print(f"\n===== {h['corp_name']} {h['stock_code']} {h['report_nm'].strip()} {h['rcept_no']}")
            print("  파싱:", json.dumps(PARSERS[kind](rows), ensure_ascii=False))
    return 0


def tags_by_code(conn) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for sql, t in (("SELECT symbol FROM my_watchlist WHERE market = 'KR'", "my"),
                   ("SELECT DISTINCT ticker FROM observations WHERE kind = 'stock' AND market = 'KR' AND ticker IS NOT NULL", "note"),
                   ("SELECT symbol FROM watchlist_candidates WHERE market = 'KR'", "cand")):
        try:
            for r in conn.execute(sql).fetchall():
                if r[0] and t not in out.setdefault(r[0], []):
                    out[r[0]].append(t)
        except Exception as e:  # noqa: BLE001 - 표가 없으면 그 표시만 빠진다
            _log(f"표시 조회 실패({type(e).__name__}) - 건너뜀")
    return out


def send_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        _log("텔레그램 미설정 - 발송 건너뜀")
        return
    body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                       "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        _log("텔레그램 발송")
    except Exception as e:  # noqa: BLE001 - 알림 실패로 수집을 실패시키지 않는다
        _log(f"텔레그램 발송 실패: {e}")


def alert_text(new: list[dict], tags: dict[str, list[str]]) -> str | None:
    hits = [d for d in new if tags.get(d["stock_code"])]
    if not hits:
        return None
    lines = [f"<b>🔔 한국 공시</b> · 관심 종목 {len(hits)}건"]
    for d in sorted(hits, key=lambda x: (x["rcept_dt"], x["corp_name"] or "")):
        tag = " · ".join(TAG_KO[t] for t in tags[d["stock_code"]])
        name = html.escape(d["corp_name"] or d["stock_code"])
        lines.append(f'{d["rcept_dt"][5:].replace("-", "/")} <a href="{DART_VIEW.format(d["rcept_no"])}">{name}</a> '
                     f'{html.escape(summary(d["kind"], d["payload"]))} · {tag}')
    return "\n".join(lines)


QUALITY_KEYS = {"contract": ("amount", "pct_of_revenue", "title"),
                "prelim": ("period_end", "revenue", "revenue_yoy_pct", "operating_income_yoy_pct"),
                "notice": ("announce_date",)}


def log_quality(conn, since: str) -> None:
    """기간 안에 저장된 공시의 칸별 빈칸 수 - 양식이 달라 못 읽는 칸이 늘면 여기서 보인다.
    잠정실적 증감률은 흑자·적자전환이면 비어 있는 게 정상이라 전환 표시가 없는 것만 센다."""
    rows = conn.execute("SELECT kind, payload, corp_name FROM kr_disclosures WHERE rcept_dt >= ?", (since,)).fetchall()
    for kind, keys in QUALITY_KEYS.items():
        ps = [(json.loads(r[1]), r[2]) for r in rows if r[0] == kind]
        miss = {}
        for k in keys:
            bad = [n for p, n in ps if p.get(k) is None and not (k.endswith("_yoy_pct") and p.get(k.replace("_pct", "_turn")))]
            if bad:
                miss[k] = f"{len(bad)} ({', '.join(b or '?' for b in bad[:4])})"
        _log(f"  {kind} {len(ps)}건 빈칸: {miss or '없음'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="오늘(KST)부터 며칠 전까지 (DART 전체 검색은 3개월까지)")
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--probe", nargs=2, metavar=("BGN", "END"))
    args = ap.parse_args()
    if args.probe:
        return probe(*args.probe)

    today = datetime.now(KST).date()
    bgn = (today - timedelta(days=args.days)).strftime("%Y%m%d")
    items = dart.list_disclosures(bgn, today.strftime("%Y%m%d"))
    targets = [(i, k) for i in items if i.get("stock_code") and (k := classify(i.get("report_nm", "")))]
    _log(f"{bgn}~ 거래소공시 {len(items)}건 중 대상 {len(targets)}건 " + str(Counter(k for _, k in targets)))

    conn = get_db()
    conn.execute(KR_DISCLOSURES_DDL)
    conn.commit()
    have = {r[0] for r in conn.execute("SELECT rcept_no FROM kr_disclosures WHERE rcept_dt >= ?",
                                       ((today - timedelta(days=args.days + 1)).isoformat(),)).fetchall()}
    now = datetime.utcnow().isoformat()
    new: list[dict] = []
    failed = 0
    todo = [(i, k) for i, k in targets if i["rcept_no"] not in have]
    for i, kind in todo:
        try:
            rows = dart.document_rows(i["rcept_no"])
        except Exception as e:  # noqa: BLE001 - 한 건 실패로 전체를 멈추지 않는다
            failed += 1
            _log(f"  {i['corp_name']} {i['rcept_no']}: 원문 실패 {type(e).__name__}: {str(e)[:100]}")
            continue
        finally:
            time.sleep(DOC_SLEEP)
        payload = PARSERS[kind](rows)
        d = {"rcept_no": i["rcept_no"], "rcept_dt": f"{i['rcept_dt'][:4]}-{i['rcept_dt'][4:6]}-{i['rcept_dt'][6:8]}",
             "stock_code": i["stock_code"], "corp_name": i.get("corp_name"), "corp_cls": i.get("corp_cls"),
             "kind": kind, "report_nm": i["report_nm"].strip(), "payload": payload}
        conn.execute("INSERT OR IGNORE INTO kr_disclosures (rcept_no, rcept_dt, stock_code, corp_name, corp_cls, kind, "
                     "report_nm, payload, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (d["rcept_no"], d["rcept_dt"], d["stock_code"], d["corp_name"], d["corp_cls"], kind,
                      d["report_nm"], json.dumps(payload, ensure_ascii=False), now))
        new.append(d)
        if len(new) % 50 == 0:
            conn.commit()
    conn.commit()
    empty = Counter(d["kind"] for d in new if all(v is None for v in d["payload"].values()))
    _log(f"새로 저장 {len(new)}건 {dict(Counter(d['kind'] for d in new))} / 원문 실패 {failed} / 못 읽은 공시 {dict(empty)}")

    log_quality(conn, (today - timedelta(days=args.days)).isoformat())

    if args.notify and new:
        text = alert_text(new, tags_by_code(conn))
        if text:
            send_telegram(text)
        else:
            _log("관심 종목 새 공시 없음 - 알림 안 보냄")
    conn.close()
    if len(todo) >= 10 and not new:
        _log("새 공시 원문을 하나도 못 받음 - 실패로 끝낸다")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
