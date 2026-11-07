"""월간 리서치 보고서 (2026-11-07, 사용자 결정 - 사이트에 흩어진 한 달치를 보고서 한 장으로).

지난달(달력 월)에 쌓인 것만 모은다 - 새로 수집하지 않는다:
  1. 이달 요약        - 코드가 고른 사실을 GPT(gpt-4o)가 3~5문장으로 잇는다(숫자 없음, 브리핑 총평과 같은 뒷손질)
  2. 시장 환경 흐름    - market_regime_weekly 주별 조합
  3. 테마 흐름        - theme_signals: 이달 라벨이 붙은 테마(주별), 실적 축 방향이 바뀐 테마
  4. 주시할 뉴스      - 라벨 붙은 테마마다 theme_news에서 기사 몇 건(briefing_news.pick_headlines, 원문 제목·링크)
  5. 테마별 기업 지도  - 라벨 붙은 테마의 가치사슬 구간별 소속 기업 + 이달 그 기업에 생긴 일(브리핑의 공시·내부자·8-K)
  6. 워치리스트 한 달  - 월초 스냅샷 대비 신규·탈락, 실적 반전 들고 남
  7. 관찰 노트 회고   - 이달 브리핑에 도착한 회고
  8. 다음 달 일정     - 관심·후보·테마 소속 종목의 실적 발표 예정 + 정해진 공시 마감
점수·순위·매수 판단 없음(원칙 1), 숫자는 저장된 값 그대로(원칙 2). 결과는 monthly_reports에 쌓는다(덮어쓰지 않음, 원칙 5).

    python scripts/generate_monthly_report.py --month 2026-10 --dry-run   # 저장·발송 없이 출력
    python scripts/generate_monthly_report.py                              # 지난달, 저장 + 텔레그램 링크
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import generate_weekly_briefing as wb  # noqa: E402 - 같은 읽기·뒷손질을 쓴다
from src.analyzers.value_chain import parse_segments  # noqa: E402

SITE = "https://u-sonar.vercel.app"
PROFILES = ROOT / "frontend" / "src" / "data" / "companyProfiles.json"
MAX_THEMES = 8          # 뉴스·기업 지도에 올릴 (테마, 시장) 수
NEWS_PER_THEME = 4
LABEL_KO = {"Early Buzz": "뉴스 선행", "Full Alignment": "동반 상승", "Quiet Strength": "숨은 강세",
            "Overheated Buzz": "기대 과열", "Full Decline": "동반 하락", "Quiet Recovery": "숨은 회복"}
ARROW_KO = {"up2": "크게 오름", "up1": "오름", "flat": "보합", "down": "내림", "na": "판단 불가"}
MK = {"US": "미국", "KR": "한국"}
# 정해진 공시 마감(분기 13F 45일, 한국 분기·반기보고서 45일, 사업보고서 90일) - 다음 달에 있으면 일정에 넣는다
FIXED_DEADLINES = {(2, 14): "미국 13F 4분기 보유 신고 마감", (5, 15): "미국 13F 1분기 마감 · 한국 1분기보고서 마감",
                   (8, 14): "미국 13F 2분기 마감 · 한국 반기보고서 마감", (11, 14): "미국 13F 3분기 마감 · 한국 3분기보고서 마감",
                   (3, 31): "한국 사업보고서 마감"}


def log(msg: str) -> None:
    print(f"[monthly] {msg}", flush=True)


def month_range(month: str) -> tuple[date, date]:
    y, m = map(int, month.split("-"))
    start = date(y, m, 1)
    end = date(y + (m == 12), m % 12 + 1, 1)
    return start, end


def prev_month(today: date) -> str:
    first = today.replace(day=1) - timedelta(days=1)
    return first.strftime("%Y-%m")


def names() -> dict[str, str]:
    try:
        p = json.loads(PROFILES.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return {f"{mk}:{sym}": (wb._clean_names([v.get("n") or ""]) or [sym])[0] for mk, d in p.items() for sym, v in d.items()}


def signal_weeks(start: date, end: date) -> list[str]:
    rows = wb.turso_exec("SELECT DISTINCT week_start FROM theme_signals WHERE week_start >= ? AND week_start < ? ORDER BY week_start",
                         [start.isoformat(), end.isoformat()])
    return [r["week_start"] for r in rows]


def briefings(weeks: list[str]) -> list[dict]:
    """그 주들의 세 축을 다룬 브리핑 = 주 시작 다음 월요일 브리핑(일요일 밤 생성)."""
    out = []
    for w in weeks:
        bw = (date.fromisoformat(w) + timedelta(days=7)).isoformat()
        rows = wb._payload(wb.turso_exec("SELECT week, payload FROM weekly_briefings WHERE week = ?", [bw]))
        if rows:
            out.append(rows[0]["_data"])
    return out


def regime_section(weeks: list[str]) -> dict:
    out: dict = {"US": [], "KR": []}
    try:
        rows = wb.turso_exec("SELECT week, market, as_of, payload FROM market_regime_weekly WHERE week IN (" + ",".join("?" * len(weeks)) + ") "
                             "ORDER BY week", weeks) if weeks else []
    except Exception:  # noqa: BLE001
        rows = []
    for r in rows:
        try:
            p = json.loads(r["payload"])
        except Exception:  # noqa: BLE001
            continue
        out.setdefault(r["market"], []).append({"week": r["week"], "as_of": r["as_of"], "combos": [c["name"] for c in p.get("combos") or []],
                                                "axes": {k: {"name": a.get("name"), "dir": a.get("dir")} for k, a in (p.get("axes") or {}).items()}})
    return out


def theme_section(weeks: list[str], tnames: dict[str, str]) -> dict:
    if not weeks:
        return {"labeled": [], "earn_turns": []}
    rows = wb.turso_exec("SELECT theme_id, market, week_start, label, news_arrow, earn_arrow, price_arrow FROM theme_signals "
                         "WHERE week_start IN (" + ",".join("?" * len(weeks)) + ") ORDER BY week_start", weeks)
    by: dict[tuple, list] = defaultdict(list)
    for r in rows:
        by[(r["theme_id"], r["market"])].append(r)
    labeled, turns = [], []
    for (tid, mk), rs in by.items():
        labs = [{"week": r["week_start"], "label": r["label"], "label_ko": LABEL_KO.get(r["label"] or "", "")} for r in rs if r["label"]]
        last = rs[-1]
        base = {"theme_id": tid, "theme": tnames.get(tid, tid), "market": mk,
                "last": {k: last[f"{k}_arrow"] for k in ("news", "earn", "price")}}
        if labs:
            labeled.append({**base, "labels": labs, "weeks_labeled": len(labs)})
        first_e, last_e = rs[0]["earn_arrow"], last["earn_arrow"]
        up = lambda a: a in ("up1", "up2")  # noqa: E731
        if first_e and last_e and (up(first_e) != up(last_e)) and "na" not in (first_e, last_e):
            turns.append({**base, "from": first_e, "to": last_e})
    labeled.sort(key=lambda x: (-x["weeks_labeled"], x["market"], x["theme"]))
    turns.sort(key=lambda x: (x["market"], x["theme"]))
    return {"labeled": labeled, "earn_turns": turns}


def news_section(themes: list[dict], weeks: list[str], members: dict, nm: dict[str, str]) -> list[dict]:
    from src.analyzers.briefing_news import pick_headlines
    out = []
    for t in themes[:MAX_THEMES]:
        rows = wb.turso_exec("SELECT title, url, source, published_at FROM theme_news WHERE theme_id = ? AND market = ? AND week_start IN ("
                             + ",".join("?" * len(weeks)) + ") ORDER BY published_at DESC LIMIT 600", [t["theme_id"], t["market"], *weeks])
        core, minor = wb.theme_keywords(t["theme_id"], [t["market"]])
        mem = wb._clean_names(nm.get(f"{t['market']}:{s}") or "" for s in members.get((t["market"], t["theme_id"])) or [])
        picked = pick_headlines(rows, [], mem, n=NEWS_PER_THEME, keywords=core, minor_keywords=minor)
        out.append({"theme_id": t["theme_id"], "theme": t["theme"], "market": t["market"], "articles": picked, "total": len(rows)})
    return out


def month_events(bs: list[dict]) -> dict[str, list[str]]:
    """브리핑들에서 종목별로 이달 생긴 일(말로) - 공시·내부자·8-K·실적 반전 신규·워치리스트 신규."""
    ev: dict[str, list[str]] = defaultdict(list)

    def add(m, s, why):
        if m and s and why not in ev[f"{m}:{s}"]:
            ev[f"{m}:{s}"].append(why)
    for b in bs:
        ins = b.get("insider_week") or {}
        for g in (ins.get("items") or []) + (ins.get("discovery") or []):
            if not wb.as_bool(g.get("all_plan")):
                add(g.get("market"), g.get("symbol"), "내부자 여러 명 매수" if (g.get("buyers") or 0) > 1 else "내부자 매수")
        kd = b.get("kr_disclosures") or {}
        for x in (kd.get("contract") or {}).get("items") or []:
            if (x.get("pct") or 0) >= 10:
                add("KR", x.get("symbol"), "큰 공급계약")
        for x in (kd.get("termination") or {}).get("items") or []:
            add("KR", x.get("symbol"), "계약 해지")
        for x in (kd.get("prelim") or {}).get("items") or []:
            if x.get("operating_income_yoy_turn"):
                add("KR", x.get("symbol"), f"잠정실적 영업이익 {x['operating_income_yoy_turn']}")
        for x in (b.get("us_8k_week") or {}).get("items") or []:
            if x.get("warn"):
                add("US", x.get("symbol"), "8-K 주의 공시")
        for x in (b.get("turnaround") or {}).get("added") or []:
            add(x.get("market"), x.get("symbol"), "실적 반전 목록에 새로 듦")
    return ev


def company_map(themes: list[dict], ev: dict[str, list[str]], nm: dict[str, str], last_week: str | None) -> list[dict]:
    import yaml
    cfg = yaml.safe_load((ROOT / "config" / "themes.yaml").read_text(encoding="utf-8")) or {}
    vc = {t["id"]: parse_segments(t.get("value_chain"))["segments"] for t in cfg.get("themes") or []}
    out = []
    for t in themes[:MAX_THEMES]:
        tid, mk = t["theme_id"], t["market"]
        run = wb.turso_exec("SELECT MAX(run_id) AS r FROM theme_members WHERE theme_id = ? AND market = ? AND approved = 1", [tid, mk])
        run_id = run[0]["r"] if run else None
        if not run_id:
            continue
        mem = wb.turso_exec("SELECT ticker, linkage FROM theme_members WHERE theme_id = ? AND market = ? AND run_id = ? AND approved = 1 "
                            "AND linkage IN ('direct','partial')", [tid, mk, run_id])
        seg = {}
        try:
            for r in wb.turso_exec("SELECT ticker, segment FROM theme_member_segments WHERE theme_id = ? AND market = ? AND run_id = ? "
                                   "ORDER BY classified_at", [tid, mk, run_id]):
                seg[r["ticker"]] = int(r["segment"])
        except Exception:  # noqa: BLE001
            pass
        sig = {}
        if last_week:
            for r in wb.turso_exec("SELECT ticker, rev_yoy, earn_status, om_status FROM theme_member_signals WHERE theme_id = ? AND market = ? "
                                   "AND week_start = ?", [tid, mk, last_week]):
                sig[r["ticker"]] = r
        groups = []
        segs = vc.get(tid) or []
        for n, label in [(s["n"], s["label"]) for s in segs] + [(0, "어느 구간에도 안 맞음")]:
            items = []
            for m in mem:
                tk = m["ticker"]
                if seg.get(tk, -1 if n else 0) != n and not (n == 0 and tk not in seg):
                    continue
                s = sig.get(tk) or {}
                items.append({"symbol": tk, "name": nm.get(f"{mk}:{tk}") or tk, "linkage": m["linkage"],
                              "rev_yoy": float(s["rev_yoy"]) if s.get("rev_yoy") not in (None, "") else None,
                              "earn_status": s.get("earn_status"), "om_status": s.get("om_status"),
                              "events": ev.get(f"{mk}:{tk}", [])})
            if items or n:
                groups.append({"n": n, "label": label, "items": sorted(items, key=lambda x: x["name"])})
        out.append({"theme_id": tid, "theme": t["theme"], "market": mk, "groups": [g for g in groups if g["items"] or g["n"]]})
    return out


def watchlist_section(start: date, end: date, nm: dict[str, str]) -> dict:
    def snap(table: str, before: str, first: bool):
        op, order = (">=", "ASC") if first else ("<", "DESC")
        rows = wb._payload(wb.turso_exec(f"SELECT week, payload FROM {table} WHERE week {op} ? ORDER BY week {order} LIMIT 1", [before]))
        return rows[0] if rows else None
    out = {}
    for key, table in (("watchlist", "watchlist_weekly_snapshots"), ("turnaround", "turnaround_weekly_snapshots")):
        try:
            a, b = snap(table, start.isoformat(), True), snap(table, end.isoformat(), False)
        except Exception:  # noqa: BLE001
            a = b = None
        if not a or not b or a["week"] == b["week"]:
            out[key] = None
            continue
        ka = {f"{x['market']}:{x['symbol']}": x for x in a["_data"]}
        kb = {f"{x['market']}:{x['symbol']}": x for x in b["_data"]}
        item = lambda k, x: {"market": x["market"], "symbol": x["symbol"], "name": x.get("name") or nm.get(k) or x["symbol"]}  # noqa: E731
        added = [item(k, x) for k, x in kb.items() if k not in ka]
        removed = [item(k, x) for k, x in ka.items() if k not in kb]
        out[key] = {"from": a["week"], "to": b["week"], "start_total": len(ka), "end_total": len(kb),
                    "added": added[:20], "added_count": len(added), "removed": removed[:20], "removed_count": len(removed)}
    return out


def reviews_section(bs: list[dict], tnames: dict[str, str], nm: dict[str, str]) -> list[dict]:
    seen, out = set(), []
    for b in bs:
        for r in b.get("observation_reviews") or []:
            k = (r.get("kind"), r.get("market"), r.get("theme_id"), r.get("ticker"), str(r.get("checkpoint")), r.get("created_at"))
            if k in seen:
                continue
            seen.add(k)
            target = tnames.get(r.get("theme_id") or "", r.get("theme_id")) if r.get("kind") == "theme" else nm.get(f"{r.get('market')}:{r.get('ticker')}", r.get("ticker"))
            res = r.get("expect_results") or {}
            out.append({"kind": r.get("kind"), "market": r.get("market"), "target": target, "checkpoint": r.get("checkpoint"),
                        "created_at": str(r.get("created_at") or "")[:10],
                        "results": [{"expect": wb.EXPECT_KO.get(r.get("kind") or "theme", {}).get(e, e), "hit": v} for e, v in res.items()]})
    return out


def calendar_section(next_start: date, next_end: date, nm: dict[str, str]) -> dict:
    tags: dict[str, list[str]] = defaultdict(list)
    for r in wb.turso_exec("SELECT market, symbol FROM my_watchlist"):
        tags[f"{r['market']}:{r['symbol']}"].append("내 관심")
    for r in wb.turso_exec("SELECT market, symbol FROM watchlist_candidates"):
        tags[f"{r['market']}:{r['symbol']}"].append("후보")
    for r in wb.turso_exec("SELECT DISTINCT market, ticker FROM theme_members WHERE approved = 1 AND linkage IN ('direct','partial')"):
        if "테마" not in tags[f"{r['market']}:{r['ticker']}"]:
            tags[f"{r['market']}:{r['ticker']}"].append("테마")
    rows = wb.turso_exec("SELECT e.market, e.ticker, e.earnings_date, e.is_estimate FROM earnings_calendar e JOIN "
                         "(SELECT market, ticker, MAX(fetched_on) AS f FROM earnings_calendar GROUP BY market, ticker) l "
                         "ON l.market = e.market AND l.ticker = e.ticker AND l.f = e.fetched_on "
                         "WHERE e.earnings_date >= ? AND e.earnings_date < ? ORDER BY e.earnings_date", [next_start.isoformat(), next_end.isoformat()])
    items = []
    for r in rows:
        k = f"{r['market']}:{r['ticker']}"
        if not tags.get(k):
            continue
        items.append({"date": r["earnings_date"], "market": r["market"], "symbol": r["ticker"], "name": nm.get(k) or r["ticker"],
                      "estimate": wb.as_bool(r.get("is_estimate")), "tags": tags[k]})
    mine_first = sorted(items, key=lambda x: (0 if "내 관심" in x["tags"] else 1 if "후보" in x["tags"] else 2, x["date"]))[:40]
    fixed = [{"date": date(next_start.year, m, d).isoformat(), "what": w} for (m, d), w in FIXED_DEADLINES.items()
             if next_start.month == m]
    return {"earnings": sorted(mine_first, key=lambda x: x["date"]), "earnings_total": len(items), "deadlines": fixed}


def summary_facts(r: dict) -> list[str]:
    facts = []
    for mk in ("US", "KR"):
        seq = [", ".join(w["combos"]) or "조합 없음" for w in r["regime"].get(mk) or []]
        if seq:
            facts.append(f"{MK[mk]} 시장 환경 주별 흐름: " + " → ".join(seq))
    for t in r["themes"]["labeled"][:8]:
        labs = sorted({LABEL_KO.get(x["label"], x["label"]) for x in t["labels"]})
        facts.append(f"{t['theme']}({MK[t['market']]}): 이달 {len(t['labels'])}주 라벨 - {', '.join(labs)}")
    for t in r["themes"]["earn_turns"][:6]:
        facts.append(f"{t['theme']}({MK[t['market']]}) 실적 축: {ARROW_KO.get(t['from'], t['from'])} → {ARROW_KO.get(t['to'], t['to'])}")
    w = r["watchlist"].get("watchlist")
    if w:
        facts.append(f"워치리스트: 신규 {'있음' if w['added_count'] else '없음'}, 탈락 {'있음' if w['removed_count'] else '없음'}")
    hits = [x for x in r["reviews"] if any(y["hit"] for y in x["results"])]
    miss = [x for x in r["reviews"] if any(y["hit"] is False for y in x["results"])]
    if r["reviews"]:
        facts.append(f"관찰 노트 회고: 기대가 맞은 것 {', '.join(x['target'] for x in hits[:4]) or '없음'} / 빗나간 것 {', '.join(x['target'] for x in miss[:4]) or '없음'}")
    return facts


def gpt_summary(facts: list[str], month: str) -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key or not facts:
        return ""
    from src.llm.openai_json import call_json, model_for
    prompt = (f"{month} 한 달 동안 리서치 도구에 쌓인 사실입니다.\n" + "\n".join(f"- {f}" for f in facts) +
              "\n\n이 사실만으로 이달 요약 3~5문장을 쓰세요. 사실을 서로 잇되 원인을 짐작하거나 전망·매수 판단을 쓰지 말고, 숫자는 쓰지 마세요. "
              "'~했다/~이다' 기사체. 라벨·조합 이름은 그대로. JSON으로만: {\"summary\": \"...\"}")
    try:
        out = call_json(model_for("briefing_comment"), "당신은 사실만 쓰는 경제 기자입니다.", prompt, api_key=key, max_output_tokens=800, temperature=0.3)
    except Exception as e:  # noqa: BLE001
        log(f"요약 실패 {type(e).__name__}")
        return ""
    text = str((out or {}).get("summary") or "")
    return wb.strip_numeric_sentences(wb.strip_speculation(wb.fix_passive(text)))


def build(month: str, use_gpt: bool = True) -> dict:
    start, end = month_range(month)
    nstart, nend = month_range(end.strftime("%Y-%m"))
    tnames = wb.load_theme_names()
    nm = names()
    weeks = signal_weeks(start, end)
    log(f"{month}: 세 축 주 {weeks}")
    bs = briefings(weeks)
    log(f"브리핑 {len(bs)}주치")
    members = wb.get_theme_members()
    themes = theme_section(weeks, tnames)
    ev = month_events(bs)
    r = {
        "month": month, "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "weeks": weeks,
        "briefing_weeks": [b.get("week") for b in bs],
        "regime": regime_section(weeks),
        "themes": themes,
        "news": news_section(themes["labeled"], weeks, members, nm),
        "company_map": company_map(themes["labeled"], ev, nm, weeks[-1] if weeks else None),
        "watchlist": watchlist_section(start, end, nm),
        "reviews": reviews_section(bs, tnames, nm),
        "calendar": calendar_section(nstart, nend, nm),
    }
    r["summary_facts"] = summary_facts(r)
    r["summary"] = gpt_summary(r["summary_facts"], month) if use_gpt else ""
    return r


def save(r: dict) -> None:
    wb.turso_exec("CREATE TABLE IF NOT EXISTS monthly_reports (month TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL, "
                  "PRIMARY KEY (month, created_at))")
    wb.turso_exec("INSERT INTO monthly_reports (month, created_at, payload) VALUES (?, ?, ?)",
                  [r["month"], datetime.now(timezone.utc).isoformat(), json.dumps(r, ensure_ascii=False)])


def telegram(r: dict) -> None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return
    y, m = r["month"].split("-")
    labeled = len(r["themes"]["labeled"])
    text = (f"<b>📚 {int(m)}월 월간 리서치 보고서</b>\n라벨 붙은 테마 {labeled}곳 · 주시할 뉴스 · 테마별 기업 지도 · 다음 달 일정\n"
            f"<a href=\"{SITE}/report?month={r['month']}\">보고서 열기</a>")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        log("텔레그램 발송")
    except Exception as e:  # noqa: BLE001
        log(f"텔레그램 실패 {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=None, help="YYYY-MM (비우면 지난달)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-gpt", action="store_true")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--first-week-only", action="store_true",
                    help="정기 실행용 - 오늘(한국 시각)이 그달 첫 7일이 아니면 아무것도 안 함")
    args = ap.parse_args()
    kst_today = (datetime.now(timezone.utc) + timedelta(hours=9)).date()
    if args.first_week_only and kst_today.day > 7:
        log(f"{kst_today}: 그달 첫 주가 아니라 건너뜀")
        return 0
    month = args.month or prev_month(kst_today)
    r = build(month, use_gpt=not args.no_gpt)
    if args.dry_run:
        print(json.dumps({k: v for k, v in r.items() if k not in ("company_map",)}, ensure_ascii=False, indent=1)[:12000])
        print("\n== 기업 지도(앞부분) ==\n" + json.dumps(r["company_map"][:2], ensure_ascii=False)[:3000])
        return 0
    save(r)
    log(f"저장 {month}")
    if not args.no_telegram:
        telegram(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
