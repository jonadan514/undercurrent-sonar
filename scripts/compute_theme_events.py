"""테마별 소속 기업 이벤트를 theme_events에 쌓는다 (2026-10-21, 사용자 결정: 테마 레이더 연결). 규칙은 src/analyzers/theme_events.py.

읽는 표: theme_members(최신 승인 run, direct+partial), kr_disclosures, us_8k_filings, insider_trades - 모두 매일 수집분.
이력 표라 덮어쓰지 않는다(원칙 5): 실행마다 computed_at이 다른 새 줄. 화면은 시장별 가장 최근 실행을 읽는다.
수집 표가 아직 없으면 그 출처만 빼고 계속한다(로그로 남김).

    python scripts/compute_theme_events.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.analyzers.theme_events import FETCH_DAYS, by_theme, insider_events, kr_event, us8k_event
from src.collectors.kr_disclosures import summary as kr_summary
from src.db.data_store import get_db

KR_UNIVERSE = ROOT / "data" / "kr_universe.json"
DDL = """
CREATE TABLE IF NOT EXISTS theme_events (
  market      TEXT NOT NULL,
  theme_id    TEXT NOT NULL,
  computed_at TEXT NOT NULL,
  counts      TEXT NOT NULL,   -- 최근 7일·30일 건수, 주별 변화(weekly·busier, 2026-10-21) JSON
  items       TEXT NOT NULL,   -- 최근 30일 이벤트 목록 JSON (공시 원문 값 그대로)
  PRIMARY KEY (market, theme_id, computed_at)
)
"""


def _log(msg: str) -> None:
    print(f"[theme-events] {msg}", flush=True)


def members_by_theme(conn, market: str) -> dict[str, list[str]]:
    rows = conn.execute(
        "WITH latest AS (SELECT theme_id, MAX(run_id) AS run_id FROM theme_members WHERE market = ? AND approved = 1 GROUP BY theme_id) "
        "SELECT m.theme_id, m.ticker FROM theme_members m JOIN latest l ON l.theme_id = m.theme_id AND l.run_id = m.run_id "
        "WHERE m.market = ? AND m.approved = 1 AND m.linkage IN ('direct', 'partial')", (market, market)).fetchall()
    out: dict[str, list[str]] = {}
    for theme_id, ticker in rows:
        out.setdefault(theme_id, []).append(ticker)
    return out


def _rows(conn, sql: str, args: tuple, cols: list[str], label: str) -> list[dict] | None:
    try:
        return [dict(zip(cols, r)) for r in conn.execute(sql, args).fetchall()]
    except Exception as e:  # noqa: BLE001 - 수집 표가 아직 없으면 그 출처만 뺀다
        _log(f"{label} 조회 실패({type(e).__name__}) - 이 출처는 빼고 계속")
        return None


def _start(conn, sql: str, args: tuple) -> str | None:
    """출처 표의 가장 이른 날짜 = 데이터 시작일. 그보다 이른 주는 주별 비교에서 '데이터 없음'(0으로 치지 않는다)."""
    try:
        r = conn.execute(sql, args).fetchone()
        return r[0] if r and r[0] else None
    except Exception:  # noqa: BLE001
        return None


def events_for(conn, market: str, since: str) -> tuple[list[dict], dict, dict]:
    """-> (이벤트 목록, 주별로 셀 (종목, 날짜), 출처별 데이터 시작일)."""
    events: list[dict] = []
    if market == "KR":
        rows = _rows(conn, "SELECT rcept_no, rcept_dt, stock_code, corp_name, kind, payload FROM kr_disclosures WHERE rcept_dt >= ?",
                     (since,), ["rcept_no", "rcept_dt", "stock_code", "corp_name", "kind", "payload"], "한국 공시") or []
        for r in rows:
            r["payload"] = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
            if (e := kr_event(r, kr_summary(r["kind"], r["payload"]))):
                events.append(e)
        disc_start = _start(conn, "SELECT MIN(rcept_dt) FROM kr_disclosures WHERE kind IN ('contract', 'prelim', 'termination', 'amend')", ())
    else:
        rows = _rows(conn, "SELECT symbol, filed_on, detail, url FROM us_8k_filings WHERE filed_on >= ?",
                     (since,), ["symbol", "filed_on", "detail", "url"], "미국 8-K") or []
        for r in rows:
            if (e := us8k_event(r, json.loads(r["detail"]))):
                events.append(e)
        disc_start = _start(conn, "SELECT MIN(filed_on) FROM us_8k_filings", ())
    ins = _rows(conn, "SELECT market, symbol, owner, role, filed_on, value, plan FROM insider_trades WHERE market = ? AND filed_on >= ?",
                (market, since), ["market", "symbol", "owner", "role", "filed_on", "value", "plan"], "내부자 매수") or []
    marks = {"disclosure": [(e["ticker"], e["date"]) for e in events],
             "insider": [(r["symbol"], r["filed_on"]) for r in ins]}   # 내부자는 공시 줄마다 - 목록은 사람별로 묶여 날짜가 하나뿐
    coverage = {"disclosure": disc_start,
                "insider": _start(conn, "SELECT MIN(filed_on) FROM insider_trades WHERE market = ?", (market,))}
    events += insider_events(ins)
    return events, marks, coverage


def main() -> int:
    today = date.today()
    since = (today - timedelta(days=FETCH_DAYS)).isoformat()
    conn = get_db()
    conn.execute(DDL)
    try:
        kr_names = {i["symbol"]: i.get("name") for i in json.loads(KR_UNIVERSE.read_text(encoding="utf-8")).get("items", [])}
    except Exception:  # noqa: BLE001
        kr_names = {}
    now = datetime.utcnow().isoformat(timespec="seconds")
    total = 0
    for market in ("US", "KR"):
        members = members_by_theme(conn, market)
        if not members:
            _log(f"{market}: 승인된 소속 없음 - 건너뜀")
            continue
        events, marks, coverage = events_for(conn, market, since)
        if market == "KR":
            for e in events:
                e["name"] = e.get("name") or kr_names.get(e["ticker"])
        result = by_theme(members, events, today, marks, coverage)
        _log(f"{market}: 데이터 시작일 공시 {coverage['disclosure']} · 내부자 {coverage['insider']}")
        for theme_id, r in result.items():
            conn.execute("INSERT OR IGNORE INTO theme_events (market, theme_id, computed_at, counts, items) VALUES (?, ?, ?, ?, ?)",
                         (market, theme_id, now, json.dumps(r["counts"], ensure_ascii=False),
                          json.dumps(r["items"], ensure_ascii=False)))
        busy = sorted(((tid, r["counts"]) for tid, r in result.items() if r["counts"]["companies_30d"]),
                      key=lambda x: -x[1]["companies_30d"])
        _log(f"{market}: 테마 {len(result)}개, 이벤트 {len(events)}건, 30일 안에 이벤트 있는 테마 {len(busy)}개")
        for tid, c in busy[:8]:
            w = c["weekly"]
            _log(f"  {tid}: 공시 주별 {w['disclosure']['weeks']}(평소 {w['disclosure']['avg']}), 내부자 주별 "
                 f"{w['insider']['weeks']}(평소 {w['insider']['avg']}), 소속 {c['members']}개 중 30일 {c['companies_30d']}개사")
        more = [tid for tid, r in result.items() if any(r["counts"]["busier"].values())]
        _log(f"{market}: 평소보다 많음 {len(more)}개 - {', '.join(more[:12])}")
        total += len(result)
    conn.commit()
    conn.close()
    if total == 0:
        _log("테마를 하나도 못 만듦 - 실패로 끝낸다")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
