"""테마별 소속 기업 이벤트 (2026-10-21, 사용자 결정: 테마 레이더 연결).

이미 모으는 회사 단위 이벤트 - 한국 공시(공급계약·해지·금액 정정·잠정실적), 미국 8-K, 내부자 장내 매수 - 를
테마 소속 기업(최신 승인 run, direct+partial - 다른 세 축과 같은 기준)으로 묶어 센다.

세 축(뉴스·실적·주가)에 더하는 넷째 축이 아니다 - 화살표·라벨·점수에 들어가지 않고(원칙 1), 건수와 원문 값만 옆에 놓는다.
실적 축은 분기 공시가 나와야 움직이는데, 공급계약·중요 계약·내부자 매수는 그 전에 나온다 - "실적 → 인데 계약이 쌓이는 테마"를
사람이 보게 하는 용도. 숫자는 공시 값 그대로(원칙 2).
"""
from __future__ import annotations

from datetime import date, timedelta

WINDOW_DAYS = 30     # 펼쳤을 때 보이는 목록 기간
ITEMS_MAX = 40       # 테마당 목록 길이
FETCH_DAYS = 35      # 원본 표에서 읽는 기간 - 이번 주 + 직전 4주(주별 변화)

# 한국 공시 종류 -> 이벤트 종류. 금액 정정은 금액이 바뀐 것만(날짜·문구 정정은 뺀다 - 브리핑과 같은 기준).
KR_KINDS = {"contract": "공급계약", "termination": "계약 해지", "amend": "계약금액 정정", "prelim": "잠정실적"}
WARN_KINDS = {"termination"}


def _since(today: date, days: int) -> str:
    return (today - timedelta(days=days)).isoformat()


def kr_event(row: dict, summary: str) -> dict | None:
    """kr_disclosures 한 줄 -> 이벤트. 보는 종류가 아니거나 금액이 그대로인 정정은 None."""
    kind, p = row["kind"], row["payload"]
    if kind not in KR_KINDS or (kind == "amend" and not p.get("amount_changed")):
        return None
    label = KR_KINDS[kind]
    text = summary[len(label):].strip() if summary.startswith(label) else summary   # 종류 이름이 요약 앞에도 있어 겹치지 않게
    return {"date": row["rcept_dt"], "ticker": row["stock_code"], "name": row.get("corp_name"), "type": "disclosure",
            "kind": label, "text": text, "warn": kind in WARN_KINDS,
            "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={row['rcept_no']}"}


def us8k_event(row: dict, detail: dict) -> dict | None:
    """us_8k_filings 한 줄 -> 이벤트. 실적 발표(2.02)만 있는 것은 None(실적 축이 따로 본다)."""
    items = [x for x in detail.get("items", []) if x["item"] != "2.02"]
    if detail.get("earnings_only") or not items:
        return None
    return {"date": row["filed_on"], "ticker": row["symbol"], "name": None, "type": "disclosure", "kind": "8-K",
            "text": ", ".join(x["label"] for x in items), "warn": any(x["warn"] for x in items), "url": row.get("url"),
            "excerpt": next((x["excerpt"] for x in items if x.get("excerpt")), None)}


def insider_events(rows: list[dict]) -> list[dict]:
    """insider_trades 줄 -> (종목, 산 사람)별로 묶은 이벤트. 금액은 공시 단가 x 주식 수 합계."""
    by: dict[tuple, dict] = {}
    for r in rows:
        key = (r["market"], r["symbol"], r["owner"])
        g = by.setdefault(key, {"date": r["filed_on"], "ticker": r["symbol"], "market": r["market"], "owner": r["owner"],
                                "role": r.get("role"), "value": 0.0, "known": False, "trades": 0, "plan": True})
        if r.get("value") is not None:
            g["value"] += float(r["value"])
            g["known"] = True
        g["trades"] += 1
        g["plan"] = g["plan"] and bool(r.get("plan"))
        if r["filed_on"] > g["date"]:
            g["date"] = r["filed_on"]
    out = []
    for g in by.values():
        role = f" ({g['role']})" if g["role"] and g["role"] != "-" else ""
        out.append({"date": g["date"], "ticker": g["ticker"], "name": None, "type": "insider", "kind": "내부자 매수",
                    "text": f"{g['owner']}{role} · {g['trades']}건" + (" · 계획 매수" if g["plan"] else ""),
                    "value": g["value"] if g["known"] else None, "warn": False, "url": None})
    return out


# ── 주별 변화 (2026-10-21, 사용자 결정: 다음 작업 1번) ─────────────────────────
# 건수만 보면 공시가 원래 흔한 테마(한국 인프라 건설: 소속 13개 중 12개사)가 늘 많아 보인다 - 그 테마 자신의 평소와 비교한다.
# 뉴스 축과 같은 방식(직전 4주 대비)이지만 화살표·라벨·점수는 만들지 않는다(원칙 1) - 주별 숫자와 "평소보다 많음" 조건 일치만.
BASE_WEEKS = 4        # 비교 기준: 직전 4주
BASE_MIN_WEEKS = 2    # 데이터가 있는 직전 주가 이보다 적으면 비교하지 않는다(기준 부족 - 0으로 치지 않는다, 원칙 4)
BUSY_RATIO = 2.0      # "평소보다 많음": 이번 주가 직전 주 평균의 2배 이상이면서
BUSY_MIN = {"disclosure": 3, "insider": 2}   # 최소 건수(공시 3건, 내부자 매수 2개사) - 평소 0~1건인 테마가 1~2건으로 튀는 것은 빼려고


def week_index(d: str, today: date) -> int | None:
    """날짜 -> 몇 주 전인가. 0 = 최근 7일(오늘 포함), 1 = 그 전 7일 ... BASE_WEEKS까지. 범위 밖이면 None."""
    days = (today - date.fromisoformat(d[:10])).days
    if days < 0:
        return 0
    k = days // 7
    return k if k <= BASE_WEEKS else None


def _week_covered(k: int, today: date, start: str | None) -> bool:
    """k주 전 칸 전체에 데이터가 있었나 - 수집 시작일(start)이 그 주 첫날보다 늦으면 그 주는 '데이터 없음'."""
    if start is None:
        return True
    first_day = today - timedelta(days=7 * k + 6)
    return date.fromisoformat(start[:10]) <= first_day


def weekly(marks: list[tuple[str, str]], today: date, start: str | None, distinct: bool) -> dict:
    """(종목, 날짜) 목록 -> 주별 건수 [이번 주, 1주 전 ... 4주 전]. distinct면 종목 수(내부자 매수 '몇 개사').
    데이터가 없던 주는 None. 평균은 데이터가 있던 직전 주만으로."""
    buckets: list[set | int] = [set() if distinct else 0 for _ in range(BASE_WEEKS + 1)]
    for ticker, d in marks:
        k = week_index(d, today)
        if k is None:
            continue
        if distinct:
            buckets[k].add(ticker)
        else:
            buckets[k] += 1
    weeks = [len(b) if distinct else b for b in buckets]
    weeks = [w if k == 0 or _week_covered(k, today, start) else None for k, w in enumerate(weeks)]
    base = [w for w in weeks[1:] if w is not None]
    avg = sum(base) / len(base) if len(base) >= BASE_MIN_WEEKS else None
    return {"weeks": weeks, "base_weeks": len(base), "avg": round(avg, 2) if avg is not None else None}


def busier(w: dict, kind: str) -> bool:
    """이번 주가 평소보다 많은가 - 조건 일치일 뿐 판정·점수 아님. 비교 기준이 부족하면 False."""
    now, avg = w["weeks"][0], w["avg"]
    return avg is not None and now >= BUSY_MIN[kind] and now >= BUSY_RATIO * avg


def by_theme(members: dict[str, list[str]], events: list[dict], today: date,
             marks: dict[str, list[tuple[str, str]]] | None = None, coverage: dict[str, str | None] | None = None) -> dict[str, dict]:
    """테마 -> 최근 7일·30일 건수, 주별 변화, 30일 목록. 이벤트가 하나도 없는 테마도 0으로 둔다(빈 것과 데이터 없음을 구분하려고 -
    수집이 안 된 시장은 호출하는 쪽이 아예 넣지 않는다).
    marks: 주별로 셀 (종목, 날짜) - {"disclosure": [...], "insider": [...]}. 내부자는 공시 줄마다(목록은 사람별로 묶여 날짜가 하나뿐이라).
           없으면 events에서 만든다. coverage: 출처별 데이터 시작일 - 그보다 이른 주는 '데이터 없음'."""
    window = _since(today, WINDOW_DAYS)
    if marks is None:
        marks = {"disclosure": [(e["ticker"], e["date"]) for e in events if e["type"] != "insider"],
                 "insider": [(e["ticker"], e["date"]) for e in events if e["type"] == "insider"]}
    coverage = coverage or {}
    by_ticker: dict[str, list[dict]] = {}
    for e in events:
        if e["date"] >= window:
            by_ticker.setdefault(e["ticker"], []).append(e)
    marks_by = {kind: {} for kind in marks}
    for kind, ms in marks.items():
        for t, d in ms:
            marks_by[kind].setdefault(t, []).append((t, d))
    out = {}
    for theme_id, tickers in members.items():
        tset = set(tickers)
        evs = sorted((e for t in tset for e in by_ticker.get(t, [])), key=lambda e: (e["date"], e["ticker"]), reverse=True)
        cnt = {"disclosure_30d": 0, "warn_30d": 0}
        ins30, cos30 = set(), set()
        for e in evs:
            cos30.add(e["ticker"])
            if e["type"] == "insider":
                ins30.add(e["ticker"])
            else:
                cnt["disclosure_30d"] += 1
            cnt["warn_30d"] += int(e["warn"])
        wk = {kind: weekly([m for t in tset for m in marks_by.get(kind, {}).get(t, [])], today, coverage.get(kind),
                           distinct=(kind == "insider"))
              for kind in ("disclosure", "insider")}
        cnt.update({"disclosure_7d": wk["disclosure"]["weeks"][0], "insider_cos_7d": wk["insider"]["weeks"][0],
                    "insider_cos_30d": len(ins30), "companies_30d": len(cos30), "members": len(tset),
                    "weekly": wk, "busier": {k: busier(wk[k], k) for k in wk}})
        out[theme_id] = {"counts": cnt, "items": evs[:ITEMS_MAX]}
    return out
