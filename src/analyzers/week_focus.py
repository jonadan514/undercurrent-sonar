"""주간 브리핑 맨 위 '이번 주 볼 것' (2026-11-15, 사용자: 사용성 논의 1번).

목적(매수할 종목 찾기·산업 흐름 파악)에 맞게 흩어진 칸에서 두 가지만 모은다 - 새 계산은 없다:
  themes - 이번 주 라벨이 붙은 테마(시장마다 2개까지). 라벨이 2개 미만인 시장은 '실적 ↑↑인데 주가는 아직'인 테마로 채운다.
  stocks - 재무 필터 통과 후보 중 테마 소속이면서 이번 주 이유가 있는 종목(워치리스트 '이번 주 볼 후보'와 같은 이유, 시장마다 3개까지).
           위 테마 소속을 먼저, 나머지는 이름순 - 이유 개수로 줄 세우지 않는다(원칙 1, 점수·순위 없음).
문장(why)은 코드가 정해진 말로만 쓴다(GPT 없음, 원칙 2).
"""
from __future__ import annotations

LABEL_ORDER = ["Quiet Strength", "Quiet Recovery", "Early Buzz", "Full Alignment", "Overheated Buzz", "Full Decline"]
LABEL_WHY = {
    "Quiet Strength": "실적은 크게 좋아졌는데 뉴스·주가는 아직 잠잠",
    "Quiet Recovery": "뉴스·주가는 내렸는데 실적은 좋아짐",
    "Early Buzz": "뉴스가 크게 늘었는데 실적은 아직 그대로",
    "Full Alignment": "뉴스·실적·주가가 함께 오름 - 이미 알려진 흐름",
    "Overheated Buzz": "뉴스·주가는 크게 올랐는데 실적은 나빠짐 - 주의",
    "Full Decline": "뉴스·실적·주가가 함께 내림 - 주의",
}
INTERIM_WHY = "실적은 크게 좋아졌는데 주가는 아직 따라오지 않음(라벨 조건에는 못 미침)"
THEMES_PER_MARKET = 2
STOCKS_PER_MARKET = 3


def focus_themes(rows: list[dict], names: dict[str, str]) -> list[dict]:
    """rows: 최근 주 theme_signals {market, theme_id, label, news, earn, price}."""
    out = []
    for mk in ("US", "KR"):
        mine = [r for r in rows if r["market"] == mk]
        labeled = sorted((r for r in mine if r.get("label")),
                         key=lambda r: (LABEL_ORDER.index(r["label"]) if r["label"] in LABEL_ORDER else 99, names.get(r["theme_id"], "")))
        pick = [{**r, "why": LABEL_WHY.get(r["label"], "")} for r in labeled[:THEMES_PER_MARKET]]
        if len(pick) < THEMES_PER_MARKET:
            interim = sorted((r for r in mine if not r.get("label") and r.get("earn") == "up2" and r.get("price") in ("flat", "down")),
                             key=lambda r: names.get(r["theme_id"], r["theme_id"]))
            pick += [{**r, "label": None, "why": INTERIM_WHY} for r in interim[:THEMES_PER_MARKET - len(pick)]]
        out += [{"market": r["market"], "theme_id": r["theme_id"], "name": names.get(r["theme_id"], r["theme_id"]),
                 "label": r.get("label"), "news": r.get("news"), "earn": r.get("earn"), "price": r.get("price"), "why": r["why"]}
                for r in pick]
    return out


def week_reasons(b: dict, cands: list[dict]) -> dict[str, list[str]]:
    """'시장:종목' -> 이번 주 이유. 워치리스트 화면 reasonsFor·weekSignalsFrom과 같은 규칙."""
    out: dict[str, list[str]] = {}

    def add(m, s, why):
        if m and s and why not in out.setdefault(f"{m}:{s}", []):
            out[f"{m}:{s}"].append(why)

    for k in (b.get("watchlist") or {}).get("added_keys") or []:
        add(*k.split(":", 1), "신규 통과")
    for c in cands:
        if c.get("valuation_tier") == "싼 편" and c.get("growth_tier") == "성장":
            add(c["market"], c["symbol"], "밸류 LOW·성장")   # 워치리스트 칩과 같은 이름
    for x in b.get("sentiment_heating") or []:
        if str(x.get("path", "")).endswith("HOT"):
            add(x.get("market"), x.get("symbol"), "관심도 HOT 진입")
    ins = b.get("insider_week") or {}
    for g in (ins.get("items") or []) + (ins.get("discovery") or []):
        if not g.get("all_plan"):
            add(g.get("market"), g.get("symbol"), "내부자 여러 명 매수" if (g.get("buyers") or 0) > 1 else "내부자 매수")
    kd = b.get("kr_disclosures") or {}
    for x in (kd.get("contract") or {}).get("items") or []:
        if (x.get("pct") or 0) >= 10:
            add("KR", x.get("symbol"), "큰 공급계약")
    for x in (kd.get("termination") or {}).get("items") or []:
        add("KR", x.get("symbol"), "계약 해지")
    for x in (b.get("us_8k_week") or {}).get("items") or []:
        if x.get("warn"):
            add("US", x.get("symbol"), "8-K 주의")
    for x in (b.get("turnaround") or {}).get("added") or []:
        add(x.get("market"), x.get("symbol"), "실적 반전 신규")
    return {k: v for k, v in out.items() if v}


def focus_stocks(b: dict, cands: list[dict], members: dict[tuple[str, str], set[str]], themes: list[dict],
                 names: dict[str, str]) -> tuple[list[dict], dict[str, int]]:
    """재무 통과 후보 중 테마 소속 + 이번 주 이유. 반환 (시장마다 STOCKS_PER_MARKET개, 시장별 전체 수)."""
    reasons = week_reasons(b, cands)
    focus_keys = {(t["market"], t["theme_id"]) for t in themes}
    theme_of: dict[str, list[str]] = {}
    for (mk, tid), syms in members.items():
        for s in syms:
            theme_of.setdefault(f"{mk}:{s}", []).append(tid)
    out, total = [], {}
    for mk in ("US", "KR"):
        rows = []
        for c in cands:
            k = f"{c['market']}:{c['symbol']}"
            if c["market"] != mk or not theme_of.get(k) or not reasons.get(k):
                continue
            tids = sorted(theme_of[k], key=lambda t: ((mk, t) not in focus_keys, names.get(t, t)))
            rows.append({"market": mk, "symbol": c["symbol"], "name": c.get("name"), "reasons": reasons[k],
                         "theme_id": tids[0], "theme": names.get(tids[0], tids[0]), "in_focus": (mk, tids[0]) in focus_keys})
        rows.sort(key=lambda x: (not x["in_focus"], x.get("name") or x["symbol"]))
        total[mk] = len(rows)
        out += rows[:STOCKS_PER_MARKET]
    return out, total
