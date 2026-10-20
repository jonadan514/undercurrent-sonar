"""미국 8-K 주요 공시 (2026-10-21, 사용자 결정: 다음 작업 2번).

한국 공급계약·잠정실적 칸의 미국판. 8-K는 회사에 중요한 일이 생기면 4영업일 안에 내는 수시 공시이고,
무슨 일인지는 "항목 번호"로 정해져 있다(SEC submissions JSON의 items, 예: "5.02,9.01").
항목 번호로 종류를 나누고, 본문에서 그 항목 첫머리 몇 문장을 원문(영어) 그대로 잘라 둔다 - 요약·번역·숫자 생성 없음(원칙 2).

뺀 항목: 7.01(Reg FD 자료)·8.01(기타)·9.01(첨부 목록)·5.03(정관)·5.07(주총 결과) - 거의 매번 붙거나 일상적이라 흐름을 가린다.
2.02(실적 발표)는 저장하지만 브리핑 목록에는 안 띄운다 - 실적 발표일 칸이 따로 있다.
"""
from __future__ import annotations

import html as _html
import re

# 항목 번호 -> (짧은 이름, 주의 표시 여부). 주의 표시는 판정이 아니라 "나쁜 쪽일 수 있는 종류"라는 분류 - 붉게 보여줄 뿐 점수 없음.
ITEMS: dict[str, tuple[str, bool]] = {
    "1.01": ("중요 계약 체결", False),
    "1.02": ("중요 계약 해지", True),
    "1.03": ("파산·회생", True),
    "1.05": ("사이버 보안 사고", True),
    "2.01": ("인수·매각 완료", False),
    "2.02": ("실적 발표", False),
    "2.03": ("대규모 차입", False),
    "2.05": ("구조조정 비용", True),
    "2.06": ("자산 손상", True),
    "3.01": ("상장 유지 기준 미달·이전", True),
    "3.02": ("비공개 주식 발행", False),
    "4.01": ("감사인 교체", True),
    "4.02": ("과거 재무제표 신뢰 불가", True),
    "5.01": ("지배권 변동", False),
    "5.02": ("임원·이사 변동", False),
}
EARNINGS_ITEM = "2.02"

# 본문에서 항목 제목을 걷어내려고 쓰는 공식 제목(SEC Form 8-K 지시문)
_TITLES = {
    "1.01": "Entry into a Material Definitive Agreement",
    "1.02": "Termination of a Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership",
    "1.05": "Material Cybersecurity Incidents",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of a Direct Financial Obligation or an Obligation under an Off-Balance Sheet Arrangement of a Registrant",
    "2.05": "Costs Associated with Exit or Disposal Activities",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting or Failure to Satisfy a Continued Listing Rule or Standard; Transfer of Listing",
    "3.02": "Unregistered Sales of Equity Securities",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements or a Related Audit Report or Completed Interim Review",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure of Directors or Certain Officers; Election of Directors; Appointment of Certain Officers; "
            "Compensatory Arrangements of Certain Officers",
}
EXCERPT_MAX = 300


def tracked_items(items: str | None) -> list[str]:
    """submissions의 items 문자열 -> 이 도구가 보는 항목 번호만, 번호 순."""
    got = {x.strip() for x in (items or "").split(",") if x.strip()}
    return sorted(got & ITEMS.keys())


def recent_8k(sub: dict, since: str) -> list[dict]:
    """submissions JSON -> 기간 안의 8-K(정정 8-K/A는 뺀다) 중 보는 항목이 하나라도 있는 것."""
    rec = (sub.get("filings") or {}).get("recent") or {}
    out = []
    for form, acc, filed, doc, items in zip(rec.get("form", []), rec.get("accessionNumber", []), rec.get("filingDate", []),
                                            rec.get("primaryDocument", []), rec.get("items", [])):
        if form != "8-K" or filed < since:
            continue
        tr = tracked_items(items)
        if tr:
            out.append({"accession": acc, "filed_on": filed, "doc": doc, "items": tr})
    return out


def html_text(raw: str) -> str:
    """8-K 본문 HTML -> 한 줄 글자. 표·스타일은 버리고 공백을 하나로."""
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = _html.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def _strip_title(seg: str, title: str) -> str:
    """seg 앞머리의 공식 제목을 글자·숫자만 맞춰 걷어낸다(구두점·대소문자·공백 차이 무시). 제목이 다르면 그대로."""
    want = [c for c in title.lower() if c.isalnum()]
    i = j = 0
    while i < len(seg) and j < len(want):
        c = seg[i].lower()
        if c.isalnum():
            if c != want[j]:
                return seg
            j += 1
        i += 1
    if j < len(want):
        return seg
    return seg[i:].lstrip(" .:;-–—")


_ITEM_HEAD = re.compile(r"(?i)\bitem\s*(\d\.\d{2})")
_STOP = re.compile(r"(?i)\bitem\s*\d\.\d{2}\b|\bsignatures?\b")


def item_section(text: str, item: str) -> str | None:
    """본문에서 'Item 5.02' 다음부터 다음 항목·서명 전까지(제목은 뺀다). 목차처럼 짧은 곳은 건너뛰고 내용이 있는 첫 곳."""
    for m in _ITEM_HEAD.finditer(text):
        if m.group(1) != item:
            continue
        rest = text[m.end():]
        stop = _STOP.search(rest)
        seg = _strip_title(rest[:stop.start()] if stop else rest, _TITLES.get(item, ""))
        if len(seg) >= 40:
            return seg
    return None


def excerpt(seg: str, limit: int = EXCERPT_MAX) -> str:
    """앞에서 limit자 안쪽, 가능하면 문장 끝에서 자른다."""
    if len(seg) <= limit:
        return seg
    cut = seg[:limit]
    end = max(cut.rfind(". "), cut.rfind("; "))
    return (cut[:end + 1] if end >= limit // 2 else cut.rstrip()) + " …"


_DEPART = re.compile(r"(?i)\b(resign\w*|retire\w*|retirement|terminat\w*|step(?:ping|ped)? down|depart\w*|"
                     r"will not stand for re-?election|not to stand for re-?election|passed away)\b")
_APPOINT = re.compile(r"(?i)\b(appoint\w*|elected|named|promot\w*|hired)\b")


def officer_change(seg: str | None) -> str | None:
    """5.02 본문의 낱말로 나눈다: 사임·퇴임 / 선임 / 둘 다 / 보상 등 그 밖. 낱말 일치일 뿐 판단이 아니다."""
    if not seg:
        return None
    d, a = bool(_DEPART.search(seg)), bool(_APPOINT.search(seg))
    if d and a:
        return "사임·선임"
    if d:
        return "사임·퇴임"
    if a:
        return "선임"
    return "보상·기타"


def describe(items: list[str], text: str | None) -> dict:
    """항목별 이름·원문 발췌. 5.02는 사임/선임 구분을 붙이고, 사임·퇴임이 들어 있으면 주의 표시."""
    out = []
    for it in items:
        name, warn = ITEMS[it]
        seg = item_section(text, it) if text else None
        sub = officer_change(seg) if it == "5.02" else None
        if sub and "사임" in sub:
            warn = True
        out.append({"item": it, "label": f"{name}({sub})" if sub else name, "warn": warn,
                    "excerpt": excerpt(seg) if seg else None})
    return {"items": out, "warn": any(x["warn"] for x in out),
            "earnings_only": items == [EARNINGS_ITEM]}
