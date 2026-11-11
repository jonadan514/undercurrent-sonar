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
import yaml

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
            add(x.get("market"), x.get("symbol"), "실적 반전 목록에 새로 오름")
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
                        "results": [{"key": e, "expect": wb.EXPECT_KO.get(r.get("kind") or "theme", {}).get(e, e), "hit": v} for e, v in res.items()]})
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


def _josa(word: str, pair: str) -> str:
    """받침 따라 '이/가'·'은/는'·'을/를' - pair는 '이가' 꼴."""
    ch = (word or " ").rstrip("'\" ")[-1:] or " "
    has = "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0
    return pair[0] if has else pair[1]


def when_in_month(weeks: list[str], week: str) -> str:
    """'월말(넷째 주)'처럼 - GPT가 '넷째 주'를 '달 내내'로 늘려 쓰지 않게 때를 같이 준다."""
    if week not in weeks:
        return "어느 한 주"
    i, n = weeks.index(week), len(weeks)
    part = "월초" if i == 0 else "월말" if i == n - 1 else "월중"
    return f"{part}({ORD[i] if i < len(ORD) else '어느 주'})"


def regime_flow(seq: list[str]) -> str:
    """주별 조합을 말 한 문장으로(GPT가 흐름을 뒤섞지 않게 문장으로 넘긴다 - 11/7 '월초 이후 뚜렷한 조합 없이 위험 회피'로 틀렸다).
    예: "첫째 주에는 '긴축 압력'이 붙었고, 둘째 주부터 '위험 회피'가 이어졌다"."""
    if not seq:
        return ""
    runs: list[list] = []   # [조합, 시작 주 번호, 주 수]
    for i, c in enumerate(seq):
        if runs and runs[-1][0] == c:
            runs[-1][2] += 1
        else:
            runs.append([c, i, 1])
    name = lambda c: f"'{c}'" if c else ""  # noqa: E731
    if len(runs) == 1:
        c = runs[0][0]
        return f"한 달 내내 {name(c)}{_josa(c, '이가')} 이어졌다" if c else "한 달 내내 뚜렷한 조합이 없었다"
    parts = []
    for k, (c, start, n) in enumerate(runs):
        when = (f"{ORD[start]}에는" if n == 1 else f"{ORD[start]}부터 {ORD[start + n - 1]}까지") if k == 0 else (f"{ORD[start]}부터" if n > 1 else f"{ORD[start]}에는")
        last = k == len(runs) - 1
        if c:
            verb = "이어졌다" if last and n > 1 else ("붙었다" if last else ("붙었고" if n == 1 else "이어졌고"))
            parts.append(f"{when} {name(c)}{_josa(c, '이가')} {verb}")
        else:
            parts.append(f"{when} 뚜렷한 조합이 {'없었다' if last else '없었고'}")
    return ", ".join(parts)


# 투자 권유·종목 추천 꼴 제목은 요약에 넘기지 않는다(화면 뉴스 칸에는 원문 그대로) - '저가매수 기회'가 요약에 옮겨 왔다(11/7)
_ADVICE_RE = re.compile(r"매수|매도|저가|기회|추천|유망|사야|팔아|\bbuy\b|\bsell\b|\bavoid\b|opportunit|could be worth|stocks? to|\bI'd\b", re.I)


# 관찰 노트 기대를 말로(기대 / 실제로 그렇게 됨 / 그렇게 안 됨). '실적↑ 유지 맞음'을 GPT가 '기대도 유지되었다'로 써서
# 결과(맞음)가 아니라 기대가 이어졌다는 말처럼 읽혔다(11/7) - 결과까지 다 쓴 문장으로 넘긴다.
EXPECT_SENT = {
    "theme": {"news_up": ("뉴스가 늘 것", "실제로 뉴스가 늘었다", "뉴스는 늘지 않았다"),
              "news_down": ("뉴스가 줄 것", "실제로 뉴스가 줄었다", "뉴스는 줄지 않았다"),
              "earn_up": ("실적이 좋아질 것", "실제로 실적이 좋아졌다", "실적은 좋아지지 않았다"),
              "earn_down": ("실적이 나빠질 것", "실제로 실적이 나빠졌다", "실적은 나빠지지 않았다"),
              "price_up": ("주가가 오를 것", "실제로 주가가 올랐다", "주가는 오르지 않았다"),
              "price_down": ("주가가 내릴 것", "실제로 주가가 내렸다", "주가는 내리지 않았다"),
              "earn_hold": ("실적 개선이 이어질 것", "실제로 실적 개선이 이어졌다", "실적 개선이 이어지지 않았다")},
    "stock": {"news_up": ("테마 뉴스가 늘 것", "실제로 테마 뉴스가 늘었다", "테마 뉴스는 늘지 않았다"),
              "news_down": ("테마 뉴스가 줄 것", "실제로 테마 뉴스가 줄었다", "테마 뉴스는 줄지 않았다"),
              "earn_up": ("실적이 테마 동료보다 좋을 것", "실제로 실적이 동료보다 좋았다", "실적이 동료보다 좋지 않았다"),
              "earn_down": ("실적이 테마 동료보다 나쁠 것", "실제로 실적이 동료보다 나빴다", "실적이 동료보다 나쁘지 않았다"),
              "price_up": ("주가가 지수보다 더 오를 것", "실제로 지수보다 더 올랐다", "지수보다 더 오르지 못했다"),
              "price_down": ("주가가 지수보다 덜 오를 것", "실제로 지수보다 덜 올랐다", "지수보다 덜 오르지는 않았다"),
              "earn_hold": ("실적이 유지될 것", "실제로 실적이 유지됐다", "실적이 유지되지 않았다")},
}


def review_sentence(kind: str, y: dict) -> str:
    """회고 한 건을 완성된 문장으로: "'뉴스가 늘 것'이라고 적어 둔 기대가 맞았다(실제로 뉴스가 늘었다)"."""
    key = y.get("key") or next((k for k, v in wb.EXPECT_KO.get(kind, {}).items() if v == y.get("expect")), None)
    sent = EXPECT_SENT.get(kind, {}).get(key or "")
    if not sent:
        what = y.get("expect")
        return f"'{what}' 기대가 {'맞았다' if y.get('hit') else '빗나갔다' if y.get('hit') is False else '아직 판단할 수 없었다'}"
    want, yes, no = sent
    if y.get("hit") is True:
        return f"'{want}'이라고 적어 둔 기대가 맞았다({yes})"
    if y.get("hit") is False:
        return f"'{want}'이라고 적어 둔 기대가 빗나갔다({no})"
    return f"'{want}'이라고 적어 둔 기대는 데이터가 모자라 판단하지 못했다"


def _ro(word: str) -> str:
    """'(으)로' - 받침 있으면 '으로'(ㄹ 받침은 '로')."""
    ch = (word or " ")[-1]
    if "가" <= ch <= "힣":
        jong = (ord(ch) - 0xAC00) % 28
        return "으로" if jong not in (0, 8) else "로"
    return "로"


def lead_flow(seq: list[str]) -> str:
    """시장 환경 흐름을 요약 첫 문장용으로 짧게: "첫째 주 '긴축 압력'에서 둘째 주부터 '위험 회피'로 바뀌었다"."""
    runs: list[list] = []
    for i, c in enumerate(seq):
        if runs and runs[-1][0] == c:
            runs[-1][2] += 1
        else:
            runs.append([c, i, 1])
    if not runs:
        return ""
    if len(runs) == 1:
        c = runs[0][0]
        return f"한 달 내내 '{c}'{_josa(c, '이가')} 이어졌다" if c else "한 달 내내 뚜렷한 조합이 없었다"
    if len(runs) == 2:
        (c1, _, n1), (c2, s2, n2) = runs
        head = ORD[0] if n1 == 1 else f"{ORD[0]}부터 {ORD[n1 - 1]}까지"
        tail = f"{ORD[s2]}부터" if n2 > 1 else f"{ORD[s2]}에"
        if c1 and c2:
            return f"{head} '{c1}'에서 {tail} '{c2}'{_ro(c2)} 바뀌었다"
        if c2:
            return f"{head}에는 뚜렷한 조합이 없다가 {tail} '{c2}'{_josa(c2, '이가')} {'이어졌다' if n2 > 1 else '붙었다'}"
        return f"{head} '{c1}'{_josa(c1, '이가')} 이어진 뒤 {tail}는 뚜렷한 조합이 없었다"
    return regime_flow(seq)


def market_lead(r: dict) -> str:
    """요약 첫 문장(시장 환경)은 코드가 쓴다 - GPT가 두 나라 흐름을 '긴축 압력과 위험 회피라는 흐름'처럼 뭉개 틀리게 썼다(11/7).
    정해진 조합 이름과 주 순서만 쓰고 숫자·해석은 없다."""
    flows = {mk: lead_flow([", ".join(w["combos"]) for w in r["regime"].get(mk) or []]) for mk in ("US", "KR")}
    us, kr = flows["US"], flows["KR"]
    if us and kr:
        if us == kr:
            return f"이달 미국과 한국 시장은 모두 {us}."
        return f"이달 미국 시장은 {us[:-1]}고, 한국 시장은 {kr}."
    one = us or kr
    return f"이달 {'미국' if us else '한국'} 시장은 {one}." if one else ""


def summary_facts(r: dict) -> list[str]:
    """요약에 넘길 사실 - 칸 순서대로 [머리]를 붙여 묶는다. 숫자는 넘기지 않는다(기사 제목 속 숫자는 문장째 걸러진다)."""
    facts: list[str] = []
    weeks = r.get("weeks") or []
    nm_of = lambda x: x.get("name") or x.get("symbol")  # noqa: E731
    facts.append("[시장]")
    for mk in ("US", "KR"):
        flow = regime_flow([", ".join(w["combos"]) for w in r["regime"].get(mk) or []])
        if flow:
            facts.append(f"{MK[mk]} 시장 환경: {flow}")
    for mk in ("KR", "US"):   # 한국 테마·미국 테마를 따로 묶는다 - 한 문장에 섞어 미국 테마가 '한국의 …'로 읽혔다(11/7)
        sub: list[str] = []
        for t in [x for x in r["themes"]["labeled"][:8] if x["market"] == mk]:
            parts = [f"{when_in_month(weeks, x['week'])} '{LABEL_KO.get(x['label'], x['label'])}'" for x in t["labels"]]
            if len(t["labels"]) == 1:
                parts[0] += "(이 한 주에만)"
            means = sorted({wb.LABEL_MEANING.get(x["label"], "").split(" - ")[0] for x in t["labels"]} - {""})   # 뒤 꼬리('시장이 덜 본 개선')는 그대로 옮겨 어색했다
            last = t.get("last") or {}
            sub.append(f"{MK[mk]} {t['theme']} 라벨이 붙은 주: {', '.join(parts)}"
                       + (f" (라벨 뜻: {' / '.join(means)})" if means else "")
                       + f" · 월말 기준 뉴스 {ARROW_KO.get(last.get('news') or 'na')}, 실적 {ARROW_KO.get(last.get('earn') or 'na')}, "
                         f"주가 {ARROW_KO.get(last.get('price') or 'na')}")
        for t in [x for x in r["themes"]["earn_turns"][:6] if x["market"] == mk]:
            sub.append(f"{MK[mk]} {t['theme']} 실적(소속 기업 실적 흐름): 월초 {ARROW_KO.get(t['from'], t['from'])} → 월말 {ARROW_KO.get(t['to'], t['to'])}"
                       " - 주가가 아니라 실적 이야기")
        for n in [x for x in (r.get("news") or [])[:6] if x["market"] == mk]:
            titles = [a["title"] for a in n["articles"] if not _ADVICE_RE.search(a["title"])][:2]
            if titles:
                sub.append(f"{MK[mk]} {n['theme']} 이달 주요 기사 제목: " + " / ".join(f"'{x}'" for x in titles))
        if sub:
            facts.append(f"[테마 - {MK[mk]}]")
            facts += sub
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
        res = [review_sentence(x.get("kind") or "theme", y) for y in x["results"]]
        if res:   # 적어 둔 기대가 없는 노트는 넘기지 않는다(맞고 틀림이 없다)
            facts.append(f"관찰 노트 회고 - {MK.get(x['market'], x['market'])} {x['target']}: " + " / ".join(res))
    facts.append("[다음 달]")
    cal = r.get("calendar") or {}
    for d in cal.get("deadlines") or []:
        facts.append(f"다음 달 마감: {d['what']}")
    mine = [x["name"] for x in cal.get("earnings") or [] if "내 관심" in x["tags"]]
    both = [x["name"] for x in cal.get("earnings") or [] if "내 관심" not in x["tags"] and {"후보", "테마"} <= set(x["tags"])]
    if mine:
        facts.append(f"다음 달 실적을 발표하는 내 워치리스트 종목: {', '.join(mine[:8])}")
    if both:
        facts.append(f"다음 달 실적을 발표하는 후보 중 테마 소속 기업: {', '.join(both[:8])}")
    return [f for i, f in enumerate(facts) if not (f.startswith("[") and (i + 1 == len(facts) or facts[i + 1].startswith("[")))]


# 문체 지침(2026-11-07 사용자 피드백: "맞았다. 조용했다."처럼 짧은 과거형만 이어져 읽기 어색 - 뉴스처럼 읽히게)
STYLE = (
    "[문체]\n"
    "- 신문 경제면 기사처럼 읽히게. 각 문단 첫 문장은 그 문단의 큰 흐름을 한 문장으로 잡고, 뒤 문장이 그것을 받쳐 준다.\n"
    "- 관련 사실 두세 개는 '~했고', '~한 반면', '~하면서', '~과 달리', '한편', '이와 함께' 같은 연결어로 한 문장에 엮는다. "
    "짧은 문장을 끊어서 나열하지 않는다.\n"
    "- 문장 끝을 다양하게: '~로 돌아섰다', '~가 이어졌다', '~을 보였다', '~에 이름을 올렸다', '~가 예정돼 있다', '~로 나타났다', "
    "'~이 붙었다', '~에서 빠졌다' 등. 같은 끝맺음('~했다', '~였다', '~맞았다')을 두 문장 연달아 쓰지 않는다.\n"
    "- '첫 주/마지막 주'는 '월초', '월말'로 바꿔 쓴다. 한 주에만 붙은 라벨을 '달 내내', '한 달 동안'처럼 늘려 쓰지 않는다.\n"
    "- '(한국)', '(미국)' 괄호 대신 '한국의 ○○', '미국 ○○'처럼 말 속에 넣는다(○○ 자리는 사실에 있는 테마 이름).\n"
    "- '뉴스↑', '실적↑ 유지' 같은 기호는 '뉴스가 늘 것이라는 기대', '실적 개선이 이어질 것이라는 기대'처럼 말로 푼다.\n"
    "- 기사 제목은 따옴표로 그대로 옮기지 않는다. 무엇을 다룬 기사인지 짧게 우리말로 풀어 쓴다"
    "(예: '짝퉁 대응과 에이피알의 성장 비결을 다룬 기사가 나왔다', '엔비디아의 중국 시장 상실을 다룬 기사가 있었다'). 영어 제목도 우리말로.\n"
    "- 실적 축이 바뀐 테마는 '○○은 소속 기업 실적이 월초 보합에서 월말 오름으로 돌아섰다'처럼 '실적'을 꼭 넣는다"
    "('○○은 오름세로 돌아섰다'만 쓰면 주가 얘기로 읽힌다).\n"
    "- 한 문장에 주어를 둘 겹치지 않는다('○○가 실적이 …' 대신 '○○는 실적이 …').\n"
    "- 예시 속 ○○·회사 이름은 자리표시일 뿐 - 사실에 없는 테마·회사·회고·기사는 절대 쓰지 않는다.\n"
    "- 라벨('숨은 강세' 등)과 시장 환경 조합('위험 회피' 등), 회사·테마 이름은 바꾸지 않는다.\n"
)
RULES = ("[지킬 것] 위 사실에 없는 내용은 쓰지 않는다. 기사 제목 속 매수·매도·투자 기회 같은 표현은 옮기지 않는다. 원인을 짐작하거나 전망·매수 판단·'주목받았다/주목할 만하다/눈여겨볼' 같은 평가를 "
         "쓰지 않는다. 숫자는 쓰지 않는다. 존댓말이 아닌 '~다' 기사체.\n")


def _clean_paras(out) -> list[str]:
    paras = (out or {}).get("paragraphs") or []
    if isinstance(paras, str):
        paras = [paras]
    return [p for p in (_drop_eval(wb.strip_numeric_sentences(wb.strip_speculation(wb.fix_passive(str(x))))) for x in paras) if p]


_EVAL_RE = re.compile(r"주목|눈여겨|관심을 끌|기대를 모|중요한 (일정|대목|변수)|가늠할 수 있")


def _drop_eval(text: str) -> str:
    """평가 문장('주목할 일정이다' 등) 빼기 - 브리핑 걸러내기(strip_speculation)가 못 잡은 꼴."""
    return " ".join(x for x in re.split(r"(?<=다\.)\s+", text.strip()) if x and not _EVAL_RE.search(x)).strip()


def missing_names(text: str, names_: list[str]) -> list[str]:
    """빠진 것. 'A|B'는 A와 B가 한 문장 안에 같이 있어야 함 - '방산'이 기업 지도 문장에만 나와 실적 축 문장이 빠진 걸 못 잡았다(11/7)."""
    sents = re.split(r"(?<=다\.)\s+", text)
    out = []
    for n in names_:
        if not n:
            continue
        parts = n.split("|")
        if not any(all(p in sent for p in parts) for sent in sents):
            out.append(parts[0])
    return out


def verbatim_titles(text: str, titles: list[str]) -> int:
    """기사 제목을 통째로 옮긴 곳 수(제목 앞 열두 글자가 그대로 들어 있으면) - 내용만 짧게 쓰라고 했다(11/7 사용자)."""
    return sum(1 for t in titles if len(t) >= 12 and t[:12] in text)


def paragraph_specs(facts: list[str]) -> list[str]:
    """있는 사실 묶음만 문단 지시로(2026-11-11) - 9월처럼 테마·기업 지도·회고가 비면 그 문단을 시키지 않는다(시키니 지어냈다)."""
    body = [f for f in facts if not f.startswith("[")]
    has_theme = any(f.startswith("[테마") for f in facts)
    has_map = any("소속 기업에 이달 생긴 일" in f or "가치사슬에서" in f or f.startswith("이달 공시·내부자") for f in body)
    has_list = any(f.startswith(("트랩 필터 통과 목록", "실적 반전 목록")) for f in body)
    has_review = any(f.startswith("관찰 노트 회고") for f in body)
    has_next = any(f.startswith("다음 달") for f in body)
    specs = []
    if has_theme:
        specs.append("테마 흐름(시장 환경 문장은 코드가 문단 맨 앞에 따로 붙이니 쓰지 말고, '테마별로는'이나 '한국에서는'처럼 테마부터 시작한다. "
                     "라벨이 붙은 테마는 라벨 뜻을 풀어서, 실적 축이 바뀐 테마는 테마마다 방향까지, 주요 기사 제목이 다룬 내용). "
                     "테마는 [테마 - 한국]과 [테마 - 미국]을 따로 문장으로 쓰고, 한 문장에 두 나라 테마를 섞지 않는다('한국에서는 …', '미국에서는 …'처럼).")
    if has_map or has_list:
        specs.append(" · ".join(x for x in ("기업 지도(소속 기업에 생긴 일, 비어 있는 구간)" if has_map else "",
                                           "워치리스트(목록에 새로 든 곳·빠진 곳)" if has_list else "") if x) + ".")
    if has_review or has_next:
        specs.append(" · ".join(x for x in ("관찰 노트 회고 결과. 사실에 적힌 '~이라고 적어 둔 기대가 맞았다/빗나갔다'와 괄호 속 실제 결과를 살려 쓰고, "
                                           "'기대가 유지되었다'처럼 결과가 흐려지는 말로 바꾸지 않는다" if has_review else "",
                                           "다음 달에 볼 일정" if has_next else "") if x) + ".")
    return specs or ["이달 사실 요약."]


# 사실 근거 검사(2026-11-11) - 9월 소급 미리보기에서 사실에 없는 'K-뷰티·바이오테크 실적 개선 기대', '방산·반도체 실적 오름',
# '관찰 노트 회고 결과 기대가 맞았다'를 지어냈다(문체 예시를 사실처럼 옮김). 요약에 나온 테마 이름·회고·기사 말이 사실 본문에 없으면 걸린다.
_GENERIC_PARTS = {"AI", "소재", "건설", "생산", "업황", "산업", "에너지", "장비", "인프라"}
_EXTRA_TERMS = ("바이오", "반도체", "뷰티", "배터리", "로봇", "관찰 노트", "회고", "기업 지도", "기대가 맞", "기대가 빗나", "라벨", "기사")


def ground_terms() -> list[str]:
    try:
        themes = yaml.safe_load((ROOT / "config" / "themes.yaml").read_text(encoding="utf-8"))["themes"]
        names_ = [t["name_ko"] for t in themes if t.get("name_ko")]
    except Exception:  # noqa: BLE001
        names_ = []
    parts = {p.strip() for n in names_ for p in re.split(r"[·(),\s]+", n) if len(p.strip()) >= 2} - _GENERIC_PARTS
    return sorted(set(names_) | parts | set(_EXTRA_TERMS), key=len, reverse=True)


def ungrounded(text: str, facts: list[str]) -> list[str]:
    """요약에 나왔는데 사실 본문([머리] 줄 빼고)에는 없는 테마 이름·회고·기사 말."""
    body = " ".join(f for f in facts if not f.startswith("["))
    return sorted({t for t in ground_terms() if t in text and t not in body})


def drop_ungrounded(text: str, facts: list[str]) -> str:
    """끝까지 남은 근거 없는 문장은 뺀다 - 문단 구분은 그대로."""
    if not ungrounded(text, facts):
        return text
    paras = []
    for para in text.split("\n\n"):
        kept = [x for x in re.split(r"(?<=다\.)\s+", para.strip()) if x and not ungrounded(x, facts)]
        if kept:
            paras.append(" ".join(kept))
    log(f"사실에 없는 말이 든 문장 뺌: {ungrounded(text, facts)}")
    return "\n\n".join(paras)


def gpt_summary(facts: list[str], month: str, required: list[str] | None = None, titles: list[str] | None = None) -> str:
    """문단 셋(시장·테마 / 기업·워치리스트 / 회고·다음 달). 초안 → 다듬기 두 번 호출. 문단은 빈 줄로 구분해 저장."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key or not facts:
        return ""
    from src.llm.openai_json import call_json, model_for
    model = model_for("briefing_comment")
    specs = paragraph_specs(facts)
    body_chars = len(" ".join(f for f in facts if not f.startswith("[")))
    min_chars = min(MIN_CHARS, int(body_chars * 0.9))   # 사실이 적은 달(2026-09 소급)에 700자를 채우려고 지어냈다 - 사실 양에 맞춘다
    prompt = (f"{month} 한 달 동안 리서치 도구에 쌓인 사실입니다. [ ]는 묶음 이름입니다.\n" + "\n".join(f if f.startswith("[") else f"- {f}" for f in facts) +
              f"\n\n이 사실만으로 월간 보고서 첫머리 요약을 문단 {len(specs)}개로 쓰세요.\n" + "\n".join(f"{i + 1}문단: {x}" for i, x in enumerate(specs)) +
              "\n사실이 없는 주제(위 문단 목록에 없는 테마 흐름·기업 지도·관찰 노트 회고·기사)는 쓰지 않는다. 사실이 적으면 문장 수를 줄인다 - "
              "길이를 채우려고 사실에 없는 말을 더하지 않는다.\n"
              "문단마다 사실이 허락하는 만큼(많아야 다섯 문장), 테마·회사 이름을 구체적으로('여러 기업'처럼 뭉뚱그리지 말 것).\n\n" + STYLE + RULES +
              "JSON으로만: {\"paragraphs\": [" + ", ".join(['\"...\"'] * len(specs)) + "]}")
    required = required or []
    if required:
        prompt += "\n반드시 들어갈 말(테마·마감·회사 이름): " + ", ".join(x.split("|")[0] for x in required)
    best, best_key = "", None
    for attempt in range(4):   # 짧거나(MIN_CHARS 미만) 테마가 빠지면 다시 - 실행마다 들쭉날쭉했다
        try:
            out = call_json(model, "당신은 사실만 쓰는 경제 기자입니다.", prompt, api_key=key, max_output_tokens=2000, temperature=0.3)
        except Exception as e:  # noqa: BLE001
            log(f"요약 실패 {type(e).__name__}")
            continue
        text = "\n\n".join(_clean_paras(out))
        miss = missing_names(text, required)
        vt = verbatim_titles(text, titles or [])
        ug = ungrounded(text, facts)
        log(f"요약 초안 {attempt + 1}차: {len(text)}자 {sentence_count(text)}문장, 빠진 테마 {miss or '없음'}, 제목 그대로 {vt}곳, "
            f"사실에 없는 말 {ug or '없음'}")
        k = (-len(ug), -len(miss), -vt, len(text))
        if best_key is None or k > best_key:
            best, best_key = text, k
        if not ug and not miss and not vt and len(text) >= min_chars:
            break
    if not best:
        return ""
    # 다듬기 - 사실은 그대로 두고 문장 흐름만(데스크 교열). 줄거나 깨지면 초안을 쓴다.
    edit = ("아래는 월간 리서치 보고서 요약 초안입니다. 데스크 기자로서 문장만 다듬으세요. 사실을 더하거나 빼지 말고, "
            "문단 수와 문단별 내용은 그대로 둡니다. 특히 짧은 문장이 같은 끝맺음으로 이어지는 곳을 연결어로 엮고, 끝맺음을 다양하게 바꾸세요.\n\n"
            + STYLE + RULES
            + ("\n초안에 기사 제목을 따옴표째 옮긴 곳이 있으면 무엇을 다룬 기사인지 짧은 우리말로 바꾸세요.\n"
               if verbatim_titles(best, titles or []) else "")
            + (f"\n초안에 빠진 것: {', '.join(missing_names(best, required))} - 아래 사실에서 찾아 알맞은 문단에 한 문장씩 넣으세요(이것만은 더해도 됩니다).\n"
               if missing_names(best, required) else "")
            + "\n[초안]\n" + best + "\n\n[참고 - 초안이 근거로 삼은 사실]\n" + "\n".join(f for f in facts if not f.startswith("[")) +
            "\n\nJSON으로만: {\"paragraphs\": [\"...\", \"...\", \"...\"]}")
    try:
        polished = "\n\n".join(_clean_paras(call_json(model, "당신은 경제면 데스크 기자입니다. 사실은 바꾸지 않고 문장만 다듬습니다.", edit,
                                                       api_key=key, max_output_tokens=2000, temperature=0.3)))
    except Exception as e:  # noqa: BLE001
        log(f"다듬기 실패 {type(e).__name__} - 초안 사용")
        return drop_ungrounded(best, facts)
    log(f"다듬기: {len(polished)}자 {sentence_count(polished)}문장, 같은 끝맺음 연속 {repeat_endings(polished)}곳 (초안 {repeat_endings(best)}곳)")
    np_, nb = len(polished.split("\n\n")), len(best.split("\n\n"))
    log(f"다듬기 뒤 빠진 것: {missing_names(polished, required) or '없음'}, 제목 그대로 {verbatim_titles(polished, titles or [])}곳, "
        f"문단 {np_}(초안 {nb})")
    if (np_ not in (nb, nb + 1) or len(polished) < len(best) * 0.75   # 긴 1문단을 한국·미국으로 나눠 한 문단 늘리는 건 받는다
            or len(ungrounded(polished, facts)) > len(ungrounded(best, facts))
            or len(missing_names(polished, required)) > len(missing_names(best, required))
            or verbatim_titles(polished, titles or []) > verbatim_titles(best, titles or [])):
        log("다듬기 결과가 초안과 문단 수가 다르거나, 많이 줄거나, 테마가 빠지거나, 사실에 없는 말이 늘어 초안 사용")
        return drop_ungrounded(best, facts)
    return drop_ungrounded(polished, facts)


MIN_CHARS = 700


def sentence_count(text: str) -> int:
    return len([x for x in re.split(r"(?<=다\.)\s+", text.strip()) if x.strip()]) if text.strip() else 0


def repeat_endings(text: str) -> int:
    """앞 문장과 끝맺음(마지막 세 글자)이 같은 문장 수 - 다듬기 전후 비교용 로그."""
    n = 0
    for para in text.split("\n\n"):
        ends = [x.strip()[-4:-1] for x in re.split(r"(?<=다\.)\s+", para.strip()) if x.strip()]
        n += sum(1 for a, b in zip(ends, ends[1:]) if a == b)
    return n


EVENT_ORDER = ["계약 해지", "8-K 주의 공시", "큰 공급계약", "내부자 여러 명 매수", "내부자 매수", "잠정실적", "실적 반전 목록에 새로 오름"]


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
    req = list(dict.fromkeys([t["theme"] for t in themes["labeled"][:8]] + [f"{t['theme']}|실적" for t in themes["earn_turns"][:6]]))
    # 다음 달 칸도 빠지지 않게(평가 문장을 지우다 마감·내 관심 실적 발표 문장이 같이 빠졌다) - 이름 검사 목록에 같이 넣는다
    if r["calendar"]["deadlines"]:
        req.append("마감")
    req += [x["name"] for x in r["calendar"]["earnings"] if "내 관심" in x["tags"]][:1]
    # 시장 환경은 market_lead가 쓰니 GPT에는 넘기지 않는다(두 번 쓰거나 뭉갠다)
    gpt_facts = [f for f in r["summary_facts"] if not (f == "[시장]" or f.startswith(("미국 시장 환경", "한국 시장 환경")))]
    titles = [a["title"] for n in r["news"] for a in n["articles"]]
    body = gpt_summary(gpt_facts, month, req, titles) if use_gpt else ""
    lead = market_lead(r)
    r["summary"] = (f"{lead} {body}" if lead else body) if body else ""
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
