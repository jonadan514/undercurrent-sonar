"""신호 사후 확인 (2026-10-21, 사용자 결정: 다음 작업 2번).

이 툴이 보여주는 신호가 실제로 쓸모 있었는지 나중에 데이터로 보려고, 신호가 나온 주에 그대로 적어 두고(signal_log - 덮어쓰지 않음, 원칙 5)
4주·12주 뒤 주가를 지수와 비교한다(signal_outcomes).

적는 신호 세 가지:
- insider_buy  : 그 주(월요일 전 7일)에 공시된 내부자 장내 매수 - 관심 종목(watched)과 관심 밖(새 이름)을 나눠 적는다.
- turnaround_new : 실적 반전 목록에 새로 들어온 종목(주간 스냅샷 비교).
- theme_busier : 소속 기업 공시·내부자 매수가 평소의 2배 이상이었던 테마(theme_events.busier). 결과는 소속 기업 주가 중앙값.
브리핑 다른 칸(2026-10-21 추가):
- kr_contract_big : 한국 매출 대비 10% 이상 공급계약.   - kr_termination : 한국 공급계약 해지(기대 방향 하락).
- us_8k_contract  : 미국 8-K 1.01 중요 계약 체결.        - us_8k_warn : 미국 8-K 주의 종류(해지·손상·구조조정 등, 기대 방향 하락).
- sentiment_heating : 관심도 상승(워치리스트 후보 네러티브 관심도가 그 주에 올라감).

결과는 분포(건수·중앙값·사분위)로만 보여준다 - "적중률"이나 신호 점수를 만들지 않는다(원칙 1). 신호를 더하거나 뺄 근거로 쓰는 기록이다.
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median

HORIZONS = (28, 84)   # 4주·12주(달력일)


def week_window(week: str) -> tuple[str, str]:
    """브리핑 주차(월요일) -> 그 주 신호의 공시 기간 [월요일-7일, 월요일-1일]. 브리핑이 일요일 밤에 '지난 7일'을 보는 것과 같다."""
    mon = date.fromisoformat(week)
    return (mon - timedelta(days=7)).isoformat(), (mon - timedelta(days=1)).isoformat()


def insider_signals(rows: list[dict], watched: set[str]) -> list[dict]:
    """insider_trades 줄(그 주 공시분) -> 종목별 신호 하나. watched = 관심 표시가 있는 '시장:종목'."""
    by: dict[str, dict] = {}
    for r in rows:
        key = f"{r['market']}:{r['symbol']}"
        g = by.setdefault(key, {"kind": "insider_buy", "market": r["market"], "symbol": r["symbol"],
                                "detail": {"watched": key in watched, "owners": [], "value": 0.0, "trades": 0, "all_plan": True}})
        d = g["detail"]
        if r["owner"] not in d["owners"]:
            d["owners"].append(r["owner"])
        d["value"] += float(r["value"] or 0)
        d["trades"] += 1
        d["all_plan"] = d["all_plan"] and bool(r.get("plan"))
    for g in by.values():
        d = g["detail"]
        d["buyers"] = len(d.pop("owners"))
    return list(by.values())


def turnaround_signals(current: list[dict], prev: list[dict] | None) -> list[dict]:
    """실적 반전 스냅샷 두 주 -> 새로 들어온 종목. 직전 스냅샷이 없으면 비교할 수 없어 빈 목록(전부 '새로'로 치지 않는다)."""
    if prev is None:
        return []
    prev_keys = {f"{p['market']}:{p['symbol']}" for p in prev}
    return [{"kind": "turnaround_new", "market": x["market"], "symbol": x["symbol"],
             "detail": {"basis": x.get("basis"), "yoy": x.get("yoy")}}
            for x in current if f"{x['market']}:{x['symbol']}" not in prev_keys]


def theme_signals(market: str, result: dict[str, dict], members: dict[str, list[str]], quiet: dict[str, bool]) -> list[dict]:
    """theme_events.by_theme 결과 -> '평소보다 많음' 테마. 결과 계산에 쓸 소속 기업을 그때 그대로 적어 둔다(나중에 소속이 바뀌어도).
    quiet = 그 주 세 축이 모두 보합이었나(테마 레이더 '축은 조용' 칸에 들어갔을 테마) - 나중에 나눠 보려고."""
    out = []
    for theme_id, r in result.items():
        b = r["counts"].get("busier") or {}
        if not any(b.values()):
            continue
        w = r["counts"]["weekly"]
        out.append({"kind": "theme_busier", "market": market, "symbol": theme_id,
                    "detail": {"busier": [k for k, v in b.items() if v], "quiet_axes": quiet.get(theme_id),
                               "disclosure_weeks": w["disclosure"]["weeks"], "insider_weeks": w["insider"]["weeks"],
                               "members": sorted(set(members.get(theme_id, [])))}})
    return out


# ── 브리핑 다른 칸 (2026-10-21 추가, 사용자 결정: 신호 종류 더하기) ─────────────────
# 브리핑에 나오는 칸을 같은 잣대로 보려고. 나쁜 쪽 신호(해지·8-K 주의 종류)는 '기대 방향이 하락'이라
# 초과수익이 마이너스면 신호가 맞은 쪽 - 화면에 기대 방향을 같이 적는다(판정·점수 아님).
KR_CONTRACT_BIG_PCT = 10.0   # 매출 대비 10% 이상 공급계약 - 브리핑에서 초록으로 강조하는 기준과 같다
SENTIMENT_RANK = {"COLD": 0, "WARM": 1, "HOT": 2}   # generate_weekly_briefing.SENTIMENT_RANK와 같아야 한다


def _one_per_symbol(sigs: list[dict]) -> list[dict]:
    """같은 주 같은 종목의 여러 공시는 신호 하나로(건수만 detail에). 결과는 종목 단위라 겹쳐 세면 그 종목만 무거워진다."""
    by: dict[tuple, dict] = {}
    for s in sigs:
        key = (s["kind"], s["market"], s["symbol"])
        if key in by:
            by[key]["detail"]["filings"] += 1
        else:
            by[key] = {**s, "detail": {**s["detail"], "filings": 1}}
    return list(by.values())


def kr_disclosure_signals(rows: list[dict]) -> list[dict]:
    """kr_disclosures 그 주분 -> kr_contract_big(매출 대비 10% 이상 공급계약), kr_termination(공급계약 해지 - 기대 방향 하락)."""
    out = []
    for r in rows:
        p = r["payload"]
        if r["kind"] == "contract" and (p.get("pct_of_revenue") or 0) >= KR_CONTRACT_BIG_PCT:
            out.append({"kind": "kr_contract_big", "market": "KR", "symbol": r["stock_code"],
                        "detail": {"pct": p.get("pct_of_revenue"), "amount": p.get("amount")}})
        elif r["kind"] == "termination":
            out.append({"kind": "kr_termination", "market": "KR", "symbol": r["stock_code"],
                        "detail": {"pct": p.get("pct_of_revenue"), "amount": p.get("amount")}})
    return _one_per_symbol(out)


def us8k_signals(rows: list[dict]) -> list[dict]:
    """us_8k_filings 그 주분 -> us_8k_warn(해지·파산·사이버 사고·구조조정·손상·상장 기준 미달·감사인 교체·재무제표 신뢰 불가 - 기대 방향 하락),
    us_8k_contract(1.01 중요 계약 체결). 한 공시에 둘 다 있으면 둘 다 적는다."""
    out = []
    for r in rows:
        items = r["detail"].get("items", [])
        warn = [x["item"] for x in items if x.get("warn")]
        if warn:
            out.append({"kind": "us_8k_warn", "market": "US", "symbol": r["symbol"], "detail": {"items": warn}})
        if any(x["item"] == "1.01" for x in items):
            out.append({"kind": "us_8k_contract", "market": "US", "symbol": r["symbol"], "detail": {"items": ["1.01"]}})
    return _one_per_symbol(out)


def sentiment_signals(rows: list[dict]) -> list[dict]:
    """narrative_sentiment_history 그 주분(날짜순) -> 관심도가 올라간 종목(주 첫 값보다 마지막 값이 높음 - 브리핑 '관심도 상승'과 같은 규칙)."""
    seq: dict[tuple, list[str]] = {}
    for r in rows:
        seq.setdefault((r["market"], r["symbol"]), []).append(r["sentiment"])
    out = []
    for (market, symbol), s in seq.items():
        if len(s) >= 2 and SENTIMENT_RANK.get(s[-1], 1) > SENTIMENT_RANK.get(s[0], 1):
            out.append({"kind": "sentiment_heating", "market": market, "symbol": symbol, "detail": {"path": f"{s[0]}→{s[-1]}"}})
    return out


# ── 결과 계산 ────────────────────────────────────────────────────────────────

def price_on_or_after(series: list[tuple[str, float]], d: str) -> tuple[str, float] | None:
    """(날짜, 종가) 날짜순 목록에서 d 이후 첫 거래일."""
    for day, close in series:
        if day >= d:
            return day, close
    return None


def fwd_return(series: list[tuple[str, float]], entry: str, days: int, today: date) -> float | None:
    """entry 이후 첫 거래일 종가 → entry+days 이후 첫 거래일 종가. 아직 기간이 안 지났거나 가격이 없으면 None."""
    target = (date.fromisoformat(entry) + timedelta(days=days)).isoformat()
    if today.isoformat() < target:
        return None
    a, b = price_on_or_after(series, entry), price_on_or_after(series, target)
    if not a or not b or not a[1]:
        return None
    return b[1] / a[1] - 1


def median_return(returns: list[float | None], min_n: int = 3) -> tuple[float | None, int]:
    """테마 결과 = 소속 기업 수익률 중앙값. 가격이 있는 기업이 min_n 미만이면 None(데이터부족 - 0으로 치지 않는다)."""
    vals = [r for r in returns if r is not None]
    return (median(vals) if len(vals) >= min_n else None), len(vals)


def distribution(values: list[float]) -> dict:
    """초과수익 목록 -> 건수·중앙값·사분위. 점수·적중률 없음(원칙 1)."""
    v = sorted(values)
    n = len(v)
    if n == 0:
        return {"n": 0, "median": None, "q1": None, "q3": None}

    def q(p: float) -> float:
        i = (n - 1) * p
        lo, hi = int(i), min(int(i) + 1, n - 1)
        return v[lo] + (v[hi] - v[lo]) * (i - lo)
    return {"n": n, "median": q(0.5), "q1": q(0.25), "q3": q(0.75)}
