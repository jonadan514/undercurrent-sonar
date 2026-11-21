"""검토 기록(stock_decisions) 결과 모음 - 주간 브리핑 텔레그램 한 줄·월간 보고서 칸이 같이 쓴다(2026-11-21, 사용자 요청).

결과 값은 stock_decision_outcomes(compute_decision_outcomes.py)가 채운 그대로 - 여기서 새 숫자를 만들지 않고 모으기만 한다.
'도착'은 시작일 + 28·84·182일(끝 날짜)이 그 기간 안에 들고 결과 값이 채워진 것. 결정(관심·보류·제외)별로
건수·수익률 중앙값·시장 대비 중앙값·시장보다 나았던 건수만 - 점수·적중률 없음(원칙 1, 성적표 화면과 같은 방식).
"""
from __future__ import annotations

from datetime import date, timedelta

HORIZONS = (28, 84, 182)
H_KO = {28: "4주", 84: "12주", 182: "26주"}
DEC_KO = {"watch": "관심", "hold": "보류", "pass": "제외"}
DEC_ORDER = ["watch", "hold", "pass"]
SRC_KO = {"tool": "툴 후보", "blog": "블로그·뉴스", "other": "기타"}
CHECK_KO = {"value": "밸류", "earn": "실적", "chart": "차트"}
CHECK_VAL_KO = {"good": "좋음", "mid": "보통", "bad": "나쁨"}


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _d(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def arrivals(rows: list[dict], start: date, end: date) -> list[dict]:
    """rows: stock_decisions + outcome 열(entry_date, ret_28d, mkt_28d …)을 합친 dict. [start, end)에 끝 날짜가 든 결과."""
    out = []
    for r in rows:
        entry = _d(r.get("entry_date"))
        if not entry:
            continue
        for h in HORIZONS:
            due = entry + timedelta(days=h)
            ret = _num(r.get(f"ret_{h}d"))
            if ret is None or not (start <= due < end):
                continue
            mkt = _num(r.get(f"mkt_{h}d"))
            out.append({"id": r.get("id"), "market": r.get("market"), "symbol": r.get("symbol"), "name": r.get("name"),
                        "decision": r.get("decision"), "decided_on": str(r.get("decided_on") or "")[:10], "h": h,
                        "due": due.isoformat(), "ret": ret, "mkt": mkt, "ex": None if mkt is None else ret - mkt})
    return sorted(out, key=lambda x: (x["h"], DEC_ORDER.index(x["decision"]) if x["decision"] in DEC_ORDER else 9, x["due"]))


def stats(items: list[dict]) -> list[dict]:
    """(기간, 결정)마다 건수·중앙값·시장 대비 중앙값·앞선 건수."""
    out = []
    for h in HORIZONS:
        for dec in DEC_ORDER:
            xs = [x for x in items if x["h"] == h and x["decision"] == dec]
            if not xs:
                continue
            ex = [x["ex"] for x in xs if x["ex"] is not None]
            out.append({"h": h, "decision": dec, "n": len(xs), "med": median([x["ret"] for x in xs]),
                        "med_ex": median(ex), "beat": sum(1 for e in ex if e > 0), "n_ex": len(ex)})
    return out


def next_arrival(rows: list[dict], today: date) -> dict | None:
    """아직 결과가 없는 것 중 가장 먼저 끝 날짜가 오는 (날짜, 기간, 건수). 시작가가 아직 없으면 기록일+1일로 어림."""
    best: dict[str, dict] = {}
    for r in rows:
        entry = _d(r.get("entry_date")) or ((_d(r.get("decided_on")) or today) + timedelta(days=1))
        for h in HORIZONS:
            if _num(r.get(f"ret_{h}d")) is not None:
                continue
            due = entry + timedelta(days=h)
            if due < today:
                continue
            k = due.isoformat()
            best.setdefault(k, {"date": k, "h": h, "n": 0})["n"] += 1
            break   # 한 기록은 가장 가까운 기간만
    return min(best.values(), key=lambda x: x["date"]) if best else None


def digest(rows: list[dict], start: date, end: date, today: date) -> dict | None:
    """주간·월간 공통 묶음. 기록이 하나도 없으면 None."""
    if not rows:
        return None
    arr = arrivals(rows, start, end)
    pending = sum(1 for r in rows if _num(r.get(f"ret_{HORIZONS[-1]}d")) is None)
    return {"total": len(rows), "pending": pending, "start": start.isoformat(), "end": end.isoformat(),
            "arrived": arr, "stats": stats(arr), "next": next_arrival(rows, today)}


def pct(v: float | None, signed: bool = True) -> str:
    if v is None:
        return "-"
    return f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%"


def pp(v: float | None) -> str:
    return "-" if v is None else f"{v * 100:+.1f}%p"


def stat_text(s: dict) -> str:
    """'관심 3건 +4.2% · 시장 대비 +1.1%p · 3건 중 2건 앞섬'"""
    t = f"{DEC_KO.get(s['decision'], s['decision'])} {s['n']}건 {pct(s['med'])}"
    if s["n_ex"]:
        t += f" · 시장 대비 {pp(s['med_ex'])} · {s['n_ex']}건 중 {s['beat']}건 앞섬"
    return t
