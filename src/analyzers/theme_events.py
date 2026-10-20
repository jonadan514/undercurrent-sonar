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
RECENT_DAYS = 7      # 줄에 붙는 건수 기간
ITEMS_MAX = 40       # 테마당 목록 길이

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
    return {"date": row["rcept_dt"], "ticker": row["stock_code"], "name": row.get("corp_name"), "type": "disclosure",
            "kind": KR_KINDS[kind], "text": summary, "warn": kind in WARN_KINDS,
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


def by_theme(members: dict[str, list[str]], events: list[dict], today: date) -> dict[str, dict]:
    """테마 -> 최근 7일·30일 건수와 30일 목록. 이벤트가 하나도 없는 테마도 0으로 둔다(빈 것과 데이터 없음을 구분하려고 -
    수집이 안 된 시장은 호출하는 쪽이 아예 넣지 않는다)."""
    recent, window = _since(today, RECENT_DAYS), _since(today, WINDOW_DAYS)
    by_ticker: dict[str, list[dict]] = {}
    for e in events:
        if e["date"] >= window:
            by_ticker.setdefault(e["ticker"], []).append(e)
    out = {}
    for theme_id, tickers in members.items():
        evs = sorted((e for t in set(tickers) for e in by_ticker.get(t, [])), key=lambda e: (e["date"], e["ticker"]), reverse=True)
        cnt = {"disclosure_7d": 0, "disclosure_30d": 0, "warn_30d": 0}
        ins7, ins30, cos30 = set(), set(), set()
        for e in evs:
            cos30.add(e["ticker"])
            if e["type"] == "insider":
                ins30.add(e["ticker"])
                if e["date"] >= recent:
                    ins7.add(e["ticker"])
            else:
                cnt["disclosure_30d"] += 1
                cnt["disclosure_7d"] += int(e["date"] >= recent)
            cnt["warn_30d"] += int(e["warn"])
        cnt.update({"insider_cos_7d": len(ins7), "insider_cos_30d": len(ins30), "companies_30d": len(cos30),
                    "members": len(set(tickers))})
        out[theme_id] = {"counts": cnt, "items": evs[:ITEMS_MAX]}
    return out
