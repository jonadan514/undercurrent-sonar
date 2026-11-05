"""주간 총평 '짚을 점'에 붙이는 관련 기사(2026-11-03, 사용자 결정).

기사는 코드가 고르고 제목·언론사·링크를 그대로 보여 준다 - GPT가 기사 내용을 옮겨 쓰지 않게(원칙 2: 제목의 숫자,
"~때문에" 같은 원인 해석). GPT에는 제목만 참고로 넘겨 "어떤 주제의 보도가 이어졌다" 정도로만 쓰게 한다.

- 테마: 테마 레이더가 이미 모은 그 주 기사(theme_news) - 새 수집 없음.
- 종목: 종목 이름으로 그 주 기사를 따로 검색(한국 네이버·없으면 구글, 미국 구글). 짚을 점 종목은 주에 몇 개뿐이다.
고르는 차례: 이번 주 신호가 나온 소속 종목 이름이 제목에 든 기사 → 테마 키워드(themes.yaml)가 든 기사 → 다른 소속 종목
이름이 든 기사 → 나머지, 같은 차례면 최신. 제목이 거의 같은 기사(여러 매체가 받아 쓴 것)는 하나만.
투자 의견·종목 추천성 제목("Undervalued", "목표주가", "매수" 등)은 뺀다 - 사실 보도만(11/3 미리 보기에서 "42% 저평가" 같은 제목이 섞임).
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

PER_POINT = 3

_OPINION = re.compile(r"undervalued|overvalued|fully valued|is the stock|stock could|should you|buy now|top pick|price target|"
                      r"stocks? to (buy|watch)|worth (watching|buying)|time to buy|목표주가|매수 추천|추천주|사야 할|담아야|급등주|순매수한 '?1위|투자의견", re.I)
SIMILAR = 0.75
MIN_TITLE = 8
MAX_TITLE = 90   # 속보형 영어 제목(Benzinga)은 문단만큼 길다 - 화면에서 자른다


def clean_title(title: str, source: str = "") -> str:
    """구글 뉴스 제목 끝의 ' - 언론사'를 뗀다."""
    t = (title or "").strip()
    if source and t.endswith(f" - {source}"):
        t = t[: -len(source) - 3].strip()
    else:
        t = re.sub(r"\s+-\s+[^-]{1,30}$", "", t).strip()
    return t


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z가-힣]", " ", t.lower())).strip()


def short_source(src: str) -> str:
    return re.sub(r"^www\.", "", (src or "").strip())


def pick_headlines(rows: list[dict], first_names: list[str] | None = None, other_names: list[str] | None = None,
                   n: int = PER_POINT, must_contain: str | None = None, keywords: list[str] | None = None,
                   minor_keywords: list[str] | None = None) -> list[dict]:
    """rows: title·url·source·published_at. 반환: 같은 필드(title은 정리된 것, source는 www. 뗀 것), 최대 n개.
    차례: 신호 종목 이름 → 핵심 키워드 → 다른 소속 종목 이름 → 곁가지 키워드(2026-11-05) → 나머지."""
    first = [x for x in (first_names or []) if x]
    other = [x for x in (other_names or []) if x and x not in first]
    kws = [k.lower() for k in (keywords or []) if k]
    minor = [k.lower() for k in (minor_keywords or []) if k]

    def tier(t: str) -> int:
        if any(nm in t for nm in first):
            return 0
        if any(k in t.lower() for k in kws):
            return 1
        if any(nm in t for nm in other):
            return 2
        if any(k in t.lower() for k in minor):
            return 3
        return 4

    cands = []
    for r in rows:
        t = clean_title(r.get("title") or "", r.get("source") or "")
        if len(t) < MIN_TITLE or not r.get("url"):
            continue
        if must_contain and must_contain.lower() not in t.lower():
            continue
        if _OPINION.search(t):
            continue
        if len(t) > MAX_TITLE:
            t = t[:MAX_TITLE].rstrip(" ,;:") + "…"
        cands.append({"title": t, "url": r["url"], "source": short_source(r.get("source") or ""), "published_at": r.get("published_at") or ""})
    cands.sort(key=lambda c: c["published_at"], reverse=True)
    cands.sort(key=lambda c: tier(c["title"]))   # 안정 정렬 - 같은 차례 안에서는 최신 순 유지
    # 한 종목 기사만 몰리지 않게(11/3 미리 보기: AI 반도체 3개 중 2개가 SK하이닉스) - 첫 바퀴는 이름마다 하나씩, 남으면 둘째 바퀴
    def who(t: str) -> str | None:
        return next((nm for nm in first + other if nm in t), None)

    out: list[dict] = []
    used: set[str] = set()
    for second in (False, True):
        for c in cands:
            if len(out) >= n:
                return out
            if c in out:
                continue
            nt = _norm(c["title"])
            if any(SequenceMatcher(None, nt, _norm(o["title"])).ratio() >= SIMILAR for o in out):
                continue
            w = who(c["title"])
            if not second and w and w in used:
                continue
            out.append(c)
            if w:
                used.add(w)
    return out
