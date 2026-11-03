"""주간 총평 '짚을 점'에 붙이는 관련 기사(2026-11-03, 사용자 결정).

기사는 코드가 고르고 제목·언론사·링크를 그대로 보여 준다 - GPT가 기사 내용을 옮겨 쓰지 않게(원칙 2: 제목의 숫자,
"~때문에" 같은 원인 해석). GPT에는 제목만 참고로 넘겨 "어떤 주제의 보도가 이어졌다" 정도로만 쓰게 한다.

- 테마: 테마 레이더가 이미 모은 그 주 기사(theme_news) - 새 수집 없음.
- 종목: 종목 이름으로 그 주 기사를 따로 검색(한국 네이버·없으면 구글, 미국 구글). 짚을 점 종목은 주에 몇 개뿐이다.
고르는 차례: 이번 주 신호가 나온 소속 종목 이름이 제목에 든 기사 → 다른 소속 종목 이름이 든 기사 → 나머지, 같은 차례면 최신.
제목이 거의 같은 기사(여러 매체가 받아 쓴 것)는 하나만.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

PER_POINT = 3
SIMILAR = 0.75
MIN_TITLE = 8


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


def pick_headlines(rows: list[dict], first_names: list[str] | None = None, other_names: list[str] | None = None,
                   n: int = PER_POINT, must_contain: str | None = None) -> list[dict]:
    """rows: title·url·source·published_at. 반환: 같은 필드(title은 정리된 것), 최대 n개."""
    first = [x for x in (first_names or []) if x]
    other = [x for x in (other_names or []) if x and x not in first]

    def tier(t: str) -> int:
        if any(nm in t for nm in first):
            return 0
        if any(nm in t for nm in other):
            return 1
        return 2

    cands = []
    for r in rows:
        t = clean_title(r.get("title") or "", r.get("source") or "")
        if len(t) < MIN_TITLE or not r.get("url"):
            continue
        if must_contain and must_contain.lower() not in t.lower():
            continue
        cands.append({"title": t, "url": r["url"], "source": r.get("source") or "", "published_at": r.get("published_at") or ""})
    cands.sort(key=lambda c: c["published_at"], reverse=True)
    cands.sort(key=lambda c: tier(c["title"]))   # 안정 정렬 - 같은 차례 안에서는 최신 순 유지
    out: list[dict] = []
    for c in cands:
        nt = _norm(c["title"])
        if any(SequenceMatcher(None, nt, _norm(o["title"])).ratio() >= SIMILAR for o in out):
            continue
        out.append(c)
        if len(out) >= n:
            break
    return out
