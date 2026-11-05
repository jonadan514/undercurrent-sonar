"""주간 총평의 '이번 주 짚을 점' - 여러 칸에 흩어진 사실 중 서로 겹치거나 엇갈리는 것을 코드가 찾는다(2026-11-02, 사용자 결정).

예전 총평은 화면에 이미 있는 목록(워치리스트 신규, 공시, 라벨…)을 문장으로 다시 읽어 줄 뿐이었다. 읽을거리는 칸과 칸 사이에 있다:
- 한 종목이 여러 칸에 걸림 - 같은 방향(관심도↑ + 영업이익 크게 늘어남)이거나 엇갈림(관심도↑인데 영업이익 크게 줄어듦)
- 내가 4주 전에 남긴 관찰 노트의 기대가 일어났는지 + 그 테마에 이번 주 붙은 라벨
- 매크로와 같은 이름의 테마(천연가스 가격 ↔ 천연가스·LNG 테마), 같은 테마의 미국·한국 라벨 차이, 라벨 붙은 테마 안에서 이번 주 신호가 나온 종목

여기서는 사실을 '말'로만 모은다(숫자 없음 - 원칙 2). GPT는 이 묶음을 받아 이유를 짐작하지 않고 연결만 문장으로 쓴다.
점수는 매기지 않는다(원칙 1) - 고르는 순서는 종류별로 정한 차례(PRIORITY)와 걸린 칸 수뿐이고 화면에 나가지 않는다.
"""
from __future__ import annotations

# 고르는 차례 - 내 것 먼저(내 관심 종목, 이번 주 라벨·매크로와 이어지는 내 관찰 노트), 엇갈림(가장 읽을 만함), 주의 겹침,
# 테마(라벨 + 매크로·소속 종목), 소속 종목 신호로만 이어지는 관찰 노트, 이어지는 게 없는 관찰 노트, 좋은 쪽 겹침
PRIORITY = ("mine", "review", "mixed", "warn", "theme", "review_members", "review_plain", "aligned")
MAX_POINTS = 5
MAX_STOCK_POINTS = 3

# 매크로 ↔ 같은 이름의 테마. 해석 없이 '같은 주에 나란히' 놓을 수 있는 짝만(원자재 이름이 곧 테마 이름인 것)
MACRO_THEME = {"lng_gas": ("natgas", "천연가스 가격"), "copper_metals": ("copper", "구리 가격")}

LABEL_KO = {"Early Buzz": "뉴스 선행", "Full Alignment": "동반 상승", "Quiet Strength": "숨은 강세",
            "Overheated Buzz": "기대 과열", "Full Decline": "동반 하락", "Quiet Recovery": "숨은 회복"}
# 라벨 뜻(theme_labels._RULES의 뉴스·실적·주가 조합) - 사실 문장에 바로 붙인다. 따로 넘기면 GPT가 두 시장 라벨을 섞어 풀었다
# (11/2 미리 보기: 미국 '동반 상승'·한국 '숨은 강세'를 "두 시장 모두 실적과 주가가 함께 올랐다"로)
LABEL_MEANING = {"Early Buzz": "뉴스와 주가는 올랐는데 실적은 아직 그대로",
                 "Full Alignment": "뉴스·실적·주가가 모두 오름",
                 "Quiet Strength": "실적은 크게 좋아졌는데 뉴스는 조용하고 주가도 아직 그대로",
                 "Overheated Buzz": "뉴스와 주가는 크게 올랐는데 실적은 나빠짐",
                 "Full Decline": "뉴스·실적·주가가 모두 내림",
                 "Quiet Recovery": "뉴스와 주가는 내렸는데 실적은 좋아짐"}
MARKET_KO = {"US": "미국", "KR": "한국"}
EXPECT_KO = {"news_up": "뉴스가 늘 것", "news_down": "뉴스가 줄 것", "earn_up": "실적이 좋아질 것", "earn_down": "실적이 나빠질 것",
             "price_up": "주가가 오를 것", "price_down": "주가가 내릴 것", "earn_hold": "실적 개선이 이어질 것"}
EXPECT_STOCK_KO = {"news_up": "테마 뉴스가 늘 것", "news_down": "테마 뉴스가 줄 것", "earn_up": "실적이 기대보다 좋을 것",
                   "earn_down": "실적이 기대보다 나쁠 것", "price_up": "지수보다 더 오를 것", "price_down": "지수보다 덜 오를 것",
                   "earn_hold": "실적이 유지될 것"}


def _chg_word(pct: float | None, what: str) -> tuple[int, str] | None:
    """전년 같은 분기 대비 변화율 -> (방향, 말). 작은 변화(±10% 안)는 신호로 치지 않는다."""
    if pct is None:
        return None
    if pct >= 30:
        return 1, f"{what} 크게 늘어남"
    if pct >= 10:
        return 1, f"{what} 늘어남"
    if pct <= -30:
        return -1, f"{what} 크게 줄어듦"
    if pct <= -10:
        return -1, f"{what} 줄어듦"
    return None


def stock_signals(b: dict, comment_8k: dict[str, str] | None = None) -> dict[tuple[str, str], dict]:
    """(시장, 종목) -> {"name", "signals": [(방향, 종류, 말)], "context": [말]}. 방향 +1 좋은 쪽 / -1 주의 쪽.
    종류가 같은 신호(공급계약 두 건 등)는 하나로 센다."""
    out: dict[tuple[str, str], dict] = {}
    comment_8k = comment_8k or {}

    def put(x: dict, sign: int, kind: str, text: str, market: str | None = None) -> None:
        key = (market or x.get("market") or "KR", x.get("symbol"))
        if not key[1]:
            return
        e = out.setdefault(key, {"name": None, "signals": [], "context": []})
        e["name"] = e["name"] or x.get("name") or x.get("symbol")
        if sign == 0:
            if text not in e["context"]:
                e["context"].append(text)
        elif not any(k == kind for _, k, _ in e["signals"]):
            e["signals"].append((sign, kind, text))

    wl = b.get("watchlist") or {}
    if wl.get("has_prev"):
        for x in wl.get("added") or []:
            put(x, 1, "watch", "워치리스트에 새로 들어옴(재무 필터 통과)")
        for x in wl.get("removed") or []:
            put(x, -1, "watch", "워치리스트에서 빠짐")
    for x in (b.get("turnaround") or {}).get("added") or []:
        put(x, 1, "turnaround", "실적 반전 목록에 새로 듦(3년 정체·역성장 뒤 최근 성장)")
    for x in b.get("sentiment_heating") or []:
        put(x, 1, "attention", f"관심도 상승({x.get('path')})")

    kd = b.get("kr_disclosures") or {}
    for x in (kd.get("contract") or {}).get("items") or []:
        pct = x.get("pct") or 0
        if pct >= 10:
            put(x, 1, "contract", "매출 대비 아주 큰 공급계약" if pct >= 30 else "매출 대비 큰 공급계약", "KR")
    for x in (kd.get("termination") or {}).get("items") or []:
        put(x, -1, "termination", "공급계약 해지", "KR")
    for x in (kd.get("prelim") or {}).get("items") or []:
        turn = x.get("operating_income_yoy_turn")
        rev = _chg_word(x.get("revenue_yoy_pct"), "매출")
        if turn:
            sign = 1 if "흑자" in turn and "전환" in turn else -1 if "적자" in turn else 0
            put(x, sign, "prelim", f"잠정실적 영업이익 {turn}", "KR")
            if rev and sign and rev[0] != sign:   # 흑자전환인데 매출은 줄어듦 등 - 따로 세어 엇갈림으로
                put(x, rev[0], "prelim_rev", f"잠정실적 {rev[1]}(전년 같은 분기 대비)", "KR")
            continue
        op = _chg_word(x.get("operating_income_yoy_pct"), "영업이익")
        if op and rev and op[0] != rev[0]:
            # 영업이익과 매출이 반대로 움직이면 한 신호로 묶지 않는다(2026-11-05) - 11/9 미리 보기에서 현대건설(영업이익 크게 늘어남,
            # 매출 줄어듦)이 내부자 매수와 함께 '같은 방향 신호가 겹침'으로 묶이고 총평이 매출 감소를 빼고 "좋은 신호가 겹쳤다"고 썼다
            put(x, op[0], "prelim", f"잠정실적 {op[1]}(전년 같은 분기 대비)", "KR")
            put(x, rev[0], "prelim_rev", f"잠정실적 {rev[1]}(전년 같은 분기 대비)", "KR")
        elif op:
            put(x, op[0], "prelim", f"잠정실적 {op[1]}(전년 같은 분기 대비)" + (f", {rev[1]}" if rev else ""), "KR")
        elif rev:
            put(x, 0, "prelim", f"잠정실적 {rev[1]}, 영업이익은 큰 변화 없음", "KR")

    ins = b.get("insider_week") or {}
    for g in (ins.get("items") or []) + (ins.get("discovery") or []):
        if g.get("all_plan"):
            continue   # 미리 정해 둔 계획 매수만 있으면 신호로 치지 않는다
        put(g, 1, "insider", "내부자 여러 명이 장내 매수" if (g.get("buyers") or 0) > 1 else "내부자 장내 매수")

    for x in (b.get("us_8k_week") or {}).get("items") or []:
        warns = [comment_8k.get(i.get("item"), i.get("label")) for i in x.get("items") or [] if i.get("warn")]
        if warns:
            put(x, -1, "8k", "미국 8-K 주의 공시: " + ", ".join(warns), "US")

    for x in (b.get("earnings_week") or {}).get("items") or []:
        key = (x.get("market"), x.get("symbol"))
        if key in out:   # 이미 신호가 있는 종목에만 일정으로 붙인다
            put(x, 0, "earnings", f"이번 주 실적 발표 예정({x.get('date')})")
    return out


def _stock_point(key: tuple[str, str], e: dict, mine: set[str]) -> dict | None:
    pos = [s for s in e["signals"] if s[0] > 0]
    neg = [s for s in e["signals"] if s[0] < 0]
    mk = f"{key[0]}:{key[1]}"
    facts = [t for _, _, t in e["signals"]] + e["context"]
    base = {"title_name": e["name"], "market": key[0], "symbol": key[1], "facts": facts, "n": len(e["signals"])}
    if mk in mine and e["signals"]:
        return {**base, "kind": "mine", "title": f"{e['name']} · 내 관심 종목", "note": "내가 관심 표시한 종목에 이번 주 생긴 일"}
    if pos and neg:
        return {**base, "kind": "mixed", "title": f"{e['name']} · 신호가 엇갈림",
                "note": "좋은 쪽 신호와 주의할 신호가 같은 주에 함께 나옴"}
    if len(neg) >= 2:
        return {**base, "kind": "warn", "title": f"{e['name']} · 주의 신호가 겹침", "note": "주의할 신호가 같은 주에 둘 이상"}
    fundamental = {"turnaround", "contract", "prelim", "insider", "watch"}
    if len(pos) >= 2 and any(k in fundamental for _, k, _ in pos):
        return {**base, "kind": "aligned", "title": f"{e['name']} · 같은 방향 신호가 겹침",
                "note": "좋은 쪽 신호가 같은 주에 둘 이상"}
    return None


def theme_points(b: dict, theme_names: dict[str, str], members: dict[tuple[str, str], set[str]],
                 signals: dict[tuple[str, str], dict], qual_macro=None) -> list[dict]:
    """테마 하나(미국·한국 합쳐)에 대해: 새로 붙거나 사라진 라벨, 관찰 노트 회고, 같은 이름 매크로, 이번 주 신호가 나온 소속 종목."""
    tl = b.get("theme_labels") or {}
    by: dict[str, dict] = {}

    def entry(tid: str, market: str | None = None) -> dict:
        e = by.setdefault(tid, {"labels": [], "reviews": [], "macro": None, "members": [], "markets": set()})
        if market:
            e["markets"].add(market)
        return e

    for t in tl.get("new_labels") or []:
        mean = LABEL_MEANING.get(t["label"])
        entry(t["theme_id"], t.get("market"))["labels"].append(
            f"{MARKET_KO.get(t.get('market'), '')}: '{LABEL_KO.get(t['label'], t['label'])}' 라벨이 새로 붙음" + (f" - {mean}" if mean else ""))
    for t in tl.get("dropped_labels") or []:
        entry(t["theme_id"], t.get("market"))["labels"].append(
            f"{MARKET_KO.get(t.get('market'), '')}: '{LABEL_KO.get(t['label'], t['label'])}' 라벨이 떨어짐(그 조합이 더는 아님)")
    for rv in b.get("observation_reviews") or []:
        if rv.get("kind") != "theme" or not rv.get("theme_id"):
            continue
        res = rv.get("expect_results") or {}
        said = [f"'{EXPECT_KO.get(k, k)}'이라 봤는데 " + ("판단할 데이터가 없음" if v is None else "실제로 그렇게 됨" if v else "그렇게 되지 않음")
                for k, v in res.items()]
        entry(rv["theme_id"], rv.get("market"))["reviews"].append(
            f"{MARKET_KO.get(rv.get('market'), '')} 관찰 노트({rv.get('checkpoint')}주 전): " + ("; ".join(said) if said else "기대를 적지 않음"))

    out = []
    for tid, e in by.items():
        if tid in MACRO_THEME and qual_macro:
            mkey, mname = MACRO_THEME[tid]
            word = qual_macro(mkey, (b.get("macro") or {}).get(mkey))
            if word and word != "보합":
                e["macro"] = f"같은 주 {mname} 1주 {word}"
        for m in sorted(e["markets"]):   # 라벨·노트가 있는 시장의 소속 종목만(미국 노트에 한국 종목을 잇지 않게)
            for sym in sorted(members.get((m, tid)) or []):
                s = signals.get((m, sym))
                if s and s["signals"]:
                    e["members"].append((m, f"{s['name']}: " + ", ".join(t for _, _, t in s["signals"])))
                    e.setdefault("signal_names", []).append(s["name"])
        name = theme_names.get(tid, tid)
        if len({l.split(":")[0] for l in e["labels"] if "새로 붙음" in l}) > 1:
            e["labels"].append("같은 테마인데 미국과 한국의 라벨이 다름 - 두 시장을 따로 봐야 함")
        # 시장을 앞에 붙인다(2026-11-05) - 미국 라벨 + 한국 노트인 테마에서 GPT가 한국 종목 신호를 미국 라벨 문장에 붙였다
        member_facts = []
        for mk in sorted({mk for mk, _ in e["members"]}):
            texts = [t for m2, t in e["members"] if m2 == mk][:3]
            member_facts.append(f"{MARKET_KO.get(mk, mk)} 소속 종목 중 이번 주 신호: " + " / ".join(texts))
        facts = e["labels"] + e["reviews"] + ([e["macro"]] if e["macro"] else []) + member_facts
        linked = bool(e["labels"] or e["macro"])
        if e["reviews"] and not (linked or e["members"]) and all("기대를 적지 않음" in r for r in e["reviews"]):
            continue   # 기대도 안 적었고 이번 주 이어지는 것도 없으면 할 말이 없다
        kind = ("review" if linked else "review_members" if e["members"] else "review_plain") if e["reviews"] else "theme"
        title = f"{name} 테마" + (" · 관찰 노트 회고" if e["reviews"] else "")
        if kind == "theme" and not (e["macro"] or e["members"] or len(e["labels"]) > 1):
            continue   # 라벨 하나만 새로 붙고 이어지는 게 없으면 화면의 라벨 칸으로 충분
        out.append({"kind": kind, "title": title, "facts": facts, "n": len(facts), "theme_id": tid,
                    "markets": sorted(e["markets"]), "signal_names": e.get("signal_names", []),
                    "note": "4주 전 내가 남긴 기대와 그 뒤" if e["reviews"] else "테마 라벨과 같은 주에 함께 나온 사실"})
    return out


def find_points(b: dict, theme_names: dict[str, str], members: dict[tuple[str, str], set[str]],
                mine: set[str], comment_8k: dict[str, str] | None = None, qual_macro=None) -> list[dict]:
    """짚을 점 최대 MAX_POINTS개 - PRIORITY 차례, 같은 차례면 걸린 칸이 많은 것. 종목 점은 MAX_STOCK_POINTS개까지."""
    sig = stock_signals(b, comment_8k)
    stock = [p for k, e in sig.items() if (p := _stock_point(k, e, mine))]
    themes = theme_points(b, theme_names, members, sig, qual_macro)
    order = lambda p: (PRIORITY.index(p["kind"]), -p["n"])  # noqa: E731
    stock.sort(key=order)
    picked = sorted(stock[:MAX_STOCK_POINTS] + themes, key=order)[:MAX_POINTS]
    return picked
