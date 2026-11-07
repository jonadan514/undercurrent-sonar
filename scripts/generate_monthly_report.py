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
import re
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
    out = {f"{mk}:{sym}": (wb._clean_names([v.get("n") or ""]) or [sym])[0] for mk, d in p.items() for sym, v in d.items()}
    try:  # 프로필이 없는 한국 종목은 유니버스 이름으로
        for i in json.loads(wb.KR_UNIVERSE.read_text(encoding="utf-8")).get("items", []):
            if out.get(f"KR:{i['symbol']}", i["symbol"]) == i["symbol"] and i.get("name"):   # 프로필 이름이 비어 코드가 든 것도
                out[f"KR:{i['symbol']}"] = i["name"]
    except Exception:  # noqa: BLE001
        pass
    try:  # 그래도 없으면 화면이 쓰는 한국 종목 이름표(frontend/src/lib/krStockNames.ts)
        ts = (ROOT / "frontend" / "src" / "lib" / "krStockNames.ts").read_text(encoding="utf-8")
        for code, nm_ in re.findall(r'"(\d{6})":\s*"([^"]+)"', ts):
            if out.get(f"KR:{code}", code) == code:
                out[f"KR:{code}"] = nm_
    except Exception:  # noqa: BLE001
        pass
    return out


def fill_kr_names(nm: dict[str, str], tickers: list[str]) -> None:
    """그래도 이름이 없는 한국 종목은 공시에 적힌 회사명으로(유니버스 밖 소형주)."""
    miss = sorted({t for t in tickers if f"KR:{t}" not in nm})
    if not miss:
        return
    try:
        rows = wb.turso_exec("SELECT stock_code, corp_name FROM kr_disclosures WHERE stock_code IN (" + ",".join("?" * len(miss)) + ") "
                             "AND corp_name IS NOT NULL ORDER BY rcept_dt", miss)
    except Exception:  # noqa: BLE001
        return
    for r in rows:
        nm[f"KR:{r['stock_code']}"] = r["corp_name"]


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
        # 주마다 따로 골라 한 달에 고르게(예전엔 최근 600건에서 골라 마지막 주 기사만 나왔고, 건수도 600에서 잘렸다)
        core, minor = wb.theme_keywords(t["theme_id"], [t["market"]])
        mem = wb._clean_names(nm.get(f"{t['market']}:{s}") or "" for s in members.get((t["market"], t["theme_id"])) or [])
        picked, seen = [], set()
        per_week = max(1, -(-NEWS_PER_THEME // max(1, len(weeks))))
        for w in weeks:
            rows = wb.turso_exec("SELECT title, url, source, published_at FROM theme_news WHERE theme_id = ? AND market = ? AND week_start = ? "
                                 "ORDER BY published_at DESC LIMIT 300", [t["theme_id"], t["market"], w])
            for a in pick_headlines(rows, [], mem, n=per_week + 1, keywords=core, minor_keywords=minor):
                if a["url"] not in seen and a["title"] not in seen and sum(1 for x in picked if x.get("_w") == w) < per_week:
                    seen.update((a["url"], a["title"]))
                    picked.append({**a, "_w": w})
        picked = [{k: v for k, v in a.items() if k != "_w"} for a in picked][:max(NEWS_PER_THEME, len(weeks))]
        cnt = wb.turso_exec("SELECT COUNT(*) AS n FROM theme_news WHERE theme_id = ? AND market = ? AND week_start IN ("
                            + ",".join("?" * len(weeks)) + ")", [t["theme_id"], t["market"], *weeks])
        out.append({"theme_id": t["theme_id"], "theme": t["theme"], "market": t["market"], "articles": picked,
                    "total": int(cnt[0]["n"]) if cnt else len(picked)})
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
        if mk == "KR":
            fill_kr_names(nm, [m["ticker"] for m in mem])
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


_SUFFIXES = ("corporation", "company", "incorporated", "holdings", "limited", "group", "inc", "ltd", "plc", "corp")


def tidy_name(name: str | None) -> str:
    """스냅샷 이름(30자에서 잘림) 정리 - 끝에 잘린 법인 꼬리('Cor'·'Corporatio')와 'Inc.' 같은 꼬리를 뗀다."""
    words = (name or "").strip().split()
    if len(words) > 1 and len(name or "") >= 30 and any(sfx.startswith(words[-1].lower().rstrip(".,")) for sfx in _SUFFIXES):
        words = words[:-1]
    return (wb._clean_names([" ".join(words)]) or [""])[0]


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
        # 스냅샷의 name은 30자에서 잘려 있어('The Bank of New York Mellon Cor') 프로필 이름을 먼저
        item = lambda k, x: {"market": x["market"], "symbol": x["symbol"], "name": nm.get(k) or tidy_name(x.get("name")) or x["symbol"]}  # noqa: E731
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
    rank = lambda t: 0 if "내 관심" in t else 1 if {"후보", "테마"} <= set(t) else 2 if "후보" in t else 3  # noqa: E731
    mine_first = sorted(items, key=lambda x: (rank(x["tags"]), x["date"]))[:40]
    fixed = [{"date": date(next_start.year, m, d).isoformat(), "what": w} for (m, d), w in FIXED_DEADLINES.items()
             if next_start.month == m]
    return {"earnings": sorted(mine_first, key=lambda x: x["date"]), "earnings_total": len(items), "deadlines": fixed}


ORD = ["첫째 주", "둘째 주", "셋째 주", "넷째 주", "다섯째 주"]


def ordinal_week(weeks: list[str], week: str) -> str:
    """주 번호를 말로 - GPT가 '1주'를 '한 주 동안'과 헷갈리지 않게."""
    return ORD[weeks.index(week)] if week in weeks and weeks.index(week) < len(ORD) else "어느 한 주"


def regime_flow(seq: list[str]) -> str:
    """주별 조합을 이어진 덩어리로 묶어 말로: '긴축 압력(첫 주만) → 위험 회피(이후 계속)'."""
    if not seq:
        return ""
    runs: list[list] = []
    for c in seq:
        if runs and runs[-1][0] == c:
            runs[-1][1] += 1
        else:
            runs.append([c, 1])
    if len(runs) == 1:
        return f"{runs[0][0] or '뚜렷한 조합 없음'}(한 달 내내)"
    out = []
    for i, (c, n) in enumerate(runs):
        last = i == len(runs) - 1
        how = ("첫 주만" if n == 1 else "처음 여러 주") if i == 0 else (("마지막 주" if n == 1 else "이후 계속") if last else ("한 주" if n == 1 else "여러 주"))
        out.append(f"{c or '뚜렷한 조합 없음'}({how})")
    return " → ".join(out)


def summary_facts(r: dict) -> list[str]:
    """요약에 넘길 사실 - 칸 순서대로 [머리]를 붙여 묶는다. 숫자는 넘기지 않는다(기사 제목 속 숫자는 문장째 걸러진다)."""
    facts: list[str] = []
    weeks = r.get("weeks") or []
    nm_of = lambda x: x.get("name") or x.get("symbol")  # noqa: E731
    facts.append("[시장]")
    for mk in ("US", "KR"):
        flow = regime_flow([", ".join(w["combos"]) for w in r["regime"].get(mk) or []])
        if flow:
            facts.append(f"{MK[mk]} 시장 환경 흐름: {flow}")
    facts.append("[테마]")
    for t in r["themes"]["labeled"][:8]:
        parts = [f"{ordinal_week(weeks, x['week'])} '{LABEL_KO.get(x['label'], x['label'])}'" for x in t["labels"]]
        means = sorted({wb.LABEL_MEANING.get(x["label"], "") for x in t["labels"]} - {""})
        last = t.get("last") or {}
        facts.append(f"{t['theme']}({MK[t['market']]}) 라벨이 붙은 주: {', '.join(parts)}"
                     + (f" (라벨 뜻: {' / '.join(means)})" if means else "")
                     + f" · 마지막 주 뉴스 {ARROW_KO.get(last.get('news') or 'na')}, 실적 {ARROW_KO.get(last.get('earn') or 'na')}, "
                       f"주가 {ARROW_KO.get(last.get('price') or 'na')}")
    for t in r["themes"]["earn_turns"][:6]:
        facts.append(f"{t['theme']}({MK[t['market']]}) 실적 축: 첫 주 {ARROW_KO.get(t['from'], t['from'])} → 마지막 주 {ARROW_KO.get(t['to'], t['to'])}")
    for n in (r.get("news") or [])[:6]:
        titles = [a["title"] for a in n["articles"][:2]]
        if titles:
            facts.append(f"{n['theme']}({MK[n['market']]}) 이달 주요 기사 제목: " + " / ".join(f"'{x}'" for x in titles))
    facts.append("[기업]")
    for m in r.get("company_map") or []:
        ev = [f"{it['name']} {'·'.join(it['events'])}" for g in m["groups"] for it in g["items"] if it["events"]]
        if ev:
            facts.append(f"{m['theme']}({MK[m['market']]}) 소속 기업에 이달 생긴 일: {', '.join(ev[:6])}")
        segs = [g["label"] for g in m["groups"] if g["n"] and g["items"]]
        empty = [g["label"] for g in m["groups"] if g["n"] and not g["items"]]
        if empty and segs:
            facts.append(f"{m['theme']}({MK[m['market']]}) 가치사슬에서 소속 기업이 없는 구간: {', '.join(empty)}")
    other = [x for x in r.get("month_events") or [] if not all(e.startswith("실적 반전") for e in x["events"])]
    if other:
        facts.append("이달 공시·내부자 매수 등이 있었던 종목(테마 지도 밖 포함): "
                     + ", ".join(f"{x['name']}({MK.get(x['market'], x['market'])}) {'·'.join(x['events'])}" for x in other[:10]))
    facts.append("[워치리스트·회고]")
    for key, label in (("watchlist", "트랩 필터 통과 목록"), ("turnaround", "실적 반전 목록")):
        w = (r.get("watchlist") or {}).get(key)
        if not w:
            continue
        grow = "늘었다" if w["end_total"] > w["start_total"] else "줄었다" if w["end_total"] < w["start_total"] else "그대로였다"
        facts.append(f"{label}: 한 달 사이 전체 규모가 {grow}. 새로 든 곳 예: {', '.join(nm_of(x) for x in w['added'][:6]) or '없음'}"
                     f" / 빠진 곳 예: {', '.join(nm_of(x) for x in w['removed'][:4]) or '없음'}")
    for x in r.get("reviews") or []:
        res = ", ".join(f"적어 둔 기대 '{y['expect']}' {'맞음' if y['hit'] else '빗나감' if y['hit'] is False else '판단 불가'}" for y in x["results"])
        facts.append(f"관찰 노트 회고 - {x['target']}({MK.get(x['market'], x['market'])}): {res or '적어 둔 기대 없음'}")
    facts.append("[다음 달]")
    cal = r.get("calendar") or {}
    for d in cal.get("deadlines") or []:
        facts.append(f"다음 달 마감: {d['what']}")
    mine = [x["name"] for x in cal.get("earnings") or [] if "내 관심" in x["tags"]]
    both = [x["name"] for x in cal.get("earnings") or [] if "내 관심" not in x["tags"] and {"후보", "테마"} <= set(x["tags"])]
    if mine:
        facts.append(f"다음 달 실적 발표 - 내 워치리스트: {', '.join(mine[:8])}")
    if both:
        facts.append(f"다음 달 실적 발표 - 후보이면서 테마 소속: {', '.join(both[:8])}")
    return [f for i, f in enumerate(facts) if not (f.startswith("[") and (i + 1 == len(facts) or facts[i + 1].startswith("[")))]


def gpt_summary(facts: list[str], month: str) -> str:
    """문단 셋(시장·테마 / 기업·워치리스트 / 회고·다음 달), 문단마다 세 문장 안팎. 문단은 빈 줄로 구분해 저장."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key or not facts:
        return ""
    from src.llm.openai_json import call_json, model_for
    prompt = (f"{month} 한 달 동안 리서치 도구에 쌓인 사실입니다. [ ]는 묶음 이름입니다.\n" + "\n".join(f if f.startswith("[") else f"- {f}" for f in facts) +
              "\n\n이 사실만으로 월간 보고서 첫머리 요약을 문단 셋으로 쓰세요.\n"
              "1문단: 시장 환경 흐름(미국·한국을 한 문장씩 따로)과 테마 흐름(라벨이 붙은 테마는 라벨 뜻을 풀어서, 실적 축이 바뀐 테마는 "
              "테마마다 '보합에서 오름으로'처럼 방향까지, 주요 기사 제목이 다룬 내용).\n"
              "2문단: 기업 지도와 워치리스트(소속 기업에 생긴 일, 비어 있는 구간, 목록에 새로 든 곳·빠진 곳).\n"
              "3문단: 관찰 노트 회고 결과와 다음 달에 볼 일정.\n"
              "문단마다 네 문장 이상, 위 사실의 테마·회사 이름을 구체적으로 들어 쓰세요('여러 기업'처럼 뭉뚱그리지 말 것). "
              "사실을 서로 잇되 원인을 짐작하거나 전망·매수 판단·'주목받았다/주목할 만하다' 같은 평가를 쓰지 말고, 숫자는 쓰지 마세요. "
              "사실이 없는 내용은 만들지 마세요. '~했다/~이다' 기사체. 라벨·조합·회사 이름은 그대로. "
              "JSON으로만: {\"paragraphs\": [\"...\", \"...\", \"...\"]}")
    best = ""
    for attempt in range(2):   # 너무 짧게 나오면(문장 MIN_SENTENCES 미만) 한 번 더 - 길이가 실행마다 들쭉날쭉했다
        try:
            out = call_json(model_for("briefing_comment"), "당신은 사실만 쓰는 경제 기자입니다.", prompt, api_key=key,
                            max_output_tokens=2000, temperature=0.3)
        except Exception as e:  # noqa: BLE001
            log(f"요약 실패 {type(e).__name__}")
            continue
        paras = (out or {}).get("paragraphs") or []
        if isinstance(paras, str):
            paras = [paras]
        clean = [wb.strip_numeric_sentences(wb.strip_speculation(wb.fix_passive(str(p)))) for p in paras]
        text = "\n\n".join(p for p in clean if p)
        n = sentence_count(text)
        log(f"요약 {attempt + 1}차: {len(clean)}문단 {n}문장")
        if n > sentence_count(best):
            best = text
        if n >= MIN_SENTENCES:
            break
    return best


MIN_SENTENCES = 10


def sentence_count(text: str) -> int:
    return len([x for x in re.split(r"(?<=다\.)\s+", text.strip()) if x.strip()]) if text.strip() else 0


EVENT_ORDER = ["계약 해지", "8-K 주의 공시", "큰 공급계약", "내부자 여러 명 매수", "내부자 매수", "잠정실적", "실적 반전 목록에 새로 듦"]


def event_list(ev: dict[str, list[str]], nm: dict[str, str]) -> list[dict]:
    """이달 생긴 일이 있는 종목 전체(테마 지도 밖 포함) - 공시·8-K 주의가 먼저, 실적 반전 신규만 있는 곳은 뒤로."""
    def rank(evs):
        return min((i for i, k in enumerate(EVENT_ORDER) for e in evs if e.startswith(k)), default=len(EVENT_ORDER))
    out = [{"market": k.split(":")[0], "symbol": k.split(":")[1], "name": nm.get(k) or k.split(":")[1], "events": v} for k, v in ev.items()]
    return sorted(out, key=lambda x: (rank(x["events"]), x["market"], x["name"]))[:40]


def map_themes(themes: dict) -> list[dict]:
    """기업 지도에 올릴 테마 - 라벨 붙은 테마 + 실적 축이 바뀐 테마(겹치면 한 번)."""
    seen, out = set(), []
    for t in themes["labeled"] + themes["earn_turns"]:
        k = (t["theme_id"], t["market"])
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out


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
    have = {k: sum(1 for b in bs if b.get(k)) for k in ("insider_week", "kr_disclosures", "us_8k_week", "turnaround")}
    log(f"이달 생긴 일 {len(ev)}종목 (브리핑에 칸이 있는 주: {have})")
    r = {
        "month": month, "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "weeks": weeks,
        "briefing_weeks": [b.get("week") for b in bs],
        "regime": regime_section(weeks),
        "themes": themes,
        "news": news_section(themes["labeled"], weeks, members, nm),
        "company_map": company_map(map_themes(themes), ev, nm, weeks[-1] if weeks else None),
        "watchlist": watchlist_section(start, end, nm),
        "month_events": event_list(ev, nm),
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
        print("== 이달 요약 ==\n" + (r["summary"] or "(없음)"))
        print("\n== 요약에 넘긴 사실 ==\n" + "\n".join(r["summary_facts"]))
        print(f"\n== 칸별 ==\n라벨 테마 {len(r['themes']['labeled'])} · 실적 축 바뀜 {len(r['themes']['earn_turns'])} · "
              f"기사 {sum(len(n['articles']) for n in r['news'])} · 기업 지도 {len(r['company_map'])}테마 · 회고 {len(r['reviews'])} · "
              f"일정 {len(r['calendar']['earnings'])}/{r['calendar']['earnings_total']} · 마감 {r['calendar']['deadlines']}")
        ev = [(m['theme'], it['name'], it['events']) for m in r['company_map'] for g in m['groups'] for it in g['items'] if it['events']]
        print("기업 지도 이달 생긴 일: " + json.dumps(ev[:12], ensure_ascii=False))
        print("회고: " + json.dumps(r["reviews"], ensure_ascii=False)[:1500])
        print("일정(앞): " + json.dumps(r["calendar"]["earnings"][:10], ensure_ascii=False))
        w = r["watchlist"]
        print("워치리스트: " + json.dumps({k: (v and {x: v[x] for x in v if x not in ("added", "removed")}) for k, v in w.items()}, ensure_ascii=False))
        return 0
    save(r)
    log(f"저장 {month}")
    if not args.no_telegram:
        telegram(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
