"""내부자 장내 매수 (2026-10-21, 사용자 결정: 다음 작업 1번).

임원·이사·대주주가 자기 돈으로 장내에서 산 기록만 모은다 - 회사 사정을 가장 잘 아는 사람의 매수라 "물밑 흐름" 신호.
스톡옵션 행사·증여·상속·보상 지급처럼 직접 산 게 아닌 거래는 뺀다. 판단·점수 없이 누가·언제·얼마나만(원칙 1·2).

미국: SEC Form 4 XML(ownershipDocument). 거래코드 P(Open market or private purchase)만.
      10b5-1 계획 매수(aff10b5One=1)는 미리 정해 둔 매수라 표시만 해 둔다(plan=True).
한국: DART 임원ㆍ주요주주특정증권등소유상황보고서. 개인이 내는 보고라 document.xml이 없어 웹 뷰어 원문 표를 읽는다
      (dart_client.viewer_rows). "세부변동내역"의 보고사유가 "장내매수(+)"인 줄만 - 주식매수선택권·증여·상속 등은 뺀다.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET


def _t(el, path: str) -> str | None:
    """'a/b/value' 경로의 글자. 없으면 None."""
    if el is None:
        return None
    x = el.find(path)
    if x is None or x.text is None:
        return None
    v = x.text.strip()
    return v or None


def _f(el, path: str) -> float | None:
    v = _t(el, path)
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


def _flag(el, path: str) -> bool:
    return (_t(el, path) or "").lower() in ("1", "true")


def owner_role(rel) -> str:
    """보고자 관계 -> 짧은 직함. 임원 직함이 있으면 그것, 아니면 이사·10% 대주주."""
    parts = []
    if _flag(rel, "isOfficer"):
        parts.append(_t(rel, "officerTitle") or "임원")
    if _flag(rel, "isDirector"):
        parts.append("이사")
    if _flag(rel, "isTenPercentOwner"):
        parts.append("10% 대주주")
    if not parts and _flag(rel, "isOther"):
        parts.append(_t(rel, "otherText") or "기타")
    return " · ".join(parts) or "-"


def parse_form4(xml_text: str) -> list[dict]:
    """Form 4 XML -> 장내 매수(P) 거래 목록. 보고자가 여럿(공동 보고)이면 이름을 ' / '로 잇는다."""
    root = ET.fromstring(xml_text)
    owners = root.findall("reportingOwner")
    names = " / ".join(filter(None, (_t(o, "reportingOwnerId/rptOwnerName") for o in owners))) or "-"
    role = " / ".join(dict.fromkeys(owner_role(o.find("reportingOwnerRelationship")) for o in owners)) or "-"
    plan = _flag(root, "aff10b5One")
    symbol = _t(root, "issuer/issuerTradingSymbol")
    out = []
    for i, tr in enumerate(root.findall("nonDerivativeTable/nonDerivativeTransaction")):
        if _t(tr, "transactionCoding/transactionCode") != "P":
            continue
        if _t(tr, "transactionAmounts/transactionAcquiredDisposedCode/value") not in (None, "A"):
            continue
        shares = _f(tr, "transactionAmounts/transactionShares/value")
        price = _f(tr, "transactionAmounts/transactionPricePerShare/value")
        out.append({
            "line": i,
            "symbol": symbol,
            "owner": names,
            "role": role,
            "trade_date": (_t(tr, "transactionDate/value") or "")[:10] or None,
            "shares": shares,
            "price": price,
            "value": shares * price if shares is not None and price is not None else None,
            "owned_after": _f(tr, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"),
            "direct": _t(tr, "ownershipNature/directOrIndirectOwnership/value") != "I",
            "plan": plan,
        })
    return out


def raw_xml_name(primary_document: str) -> str:
    """submissions의 primaryDocument('xslF345X05/form4.xml')는 사람이 보는 변환본 - 원본 XML은 접두 폴더를 뺀 이름."""
    return primary_document.split("/")[-1]


def cluster_buyers(trades: list[dict]) -> int:
    """같은 종목을 산 서로 다른 내부자 수 - 여러 명이 함께 사면 따로 표시한다(판단이 아니라 셈)."""
    return len({t["owner"] for t in trades})


# ── 한국 (DART 임원ㆍ주요주주 소유상황 보고, 웹 뷰어 표) ────────────────────────

# 숫자 사이 글자는 느슨하게 - 웹 뷰어 인코딩이 섞여 '년·월'이 깨져 와도 날짜는 읽히게
_KR_DATE = re.compile(r"(\d{4})\D{1,6}?(\d{1,2})\D{1,6}?(\d{1,2})")


def _kr_date(s: str | None) -> str | None:
    m = _KR_DATE.search(s or "")
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None


def _kr_num(s: str | None) -> float | None:
    t = (s or "").strip().replace(",", "")
    try:
        return float(t) if t and t != "-" else None
    except ValueError:
        return None


def _after_cell(rows: list[str], label: str) -> str | None:
    for r in rows:
        cells = [c.strip() for c in r.split("|")]
        for i, c in enumerate(cells[:-1]):
            if c.replace(" ", "").startswith(label):
                v = cells[i + 1]
                return None if not v or v == "-" else v
    return None


def clean_role(text: str | None) -> str | None:
    """웹 뷰어 글자 일부가 '?'로 깨져 오는 경우를 다듬는다. '10%'가 보이면 '10% 이상 주주', 그 밖에 깨진 글자가 있으면 버린다."""
    if not text or text.strip() in ("-", ""):
        return None
    t = text.strip()
    if "10%" in t:
        return "10% 이상 주주"
    if "?" in t or "\ufffd" in t:
        return None
    return t


def kr_role(rows: list[str]) -> str:
    """보고자 관계 -> 짧은 직함. 직위명이 있으면 그것, 주요주주면 그 구분."""
    parts = [p for p in (clean_role(_after_cell(rows, "직위명")), clean_role(_after_cell(rows, "주요주주"))) if p]
    return " · ".join(parts) or "-"


def parse_kr_ownership(rows: list[str]) -> list[dict]:
    """웹 뷰어 표 행 -> 장내 매수 줄. 줄 모양: 보고사유 | 변동일 | 종류 | 변동전 | 증감 | 변동후 | 단가 | 비고 | ..."""
    owner = _after_cell(rows, "보고자") or "-"
    role = kr_role(rows)
    out = []
    for i, r in enumerate(rows):
        cells = [c.strip() for c in r.split("|")]
        reason = cells[0].replace(" ", "") if cells else ""
        # 장내매수(+)만. 주식매수선택권(+)(스톡옵션)도 "매수"가 들어가 있어 "선택"으로 걸러낸다
        if not (reason.startswith("장내매수") or (reason.endswith("매수(+)") and "선택" not in reason
                                                  and not reason.startswith("주식"))) or len(cells) < 7:
            continue
        shares, price = _kr_num(cells[4]), _kr_num(cells[6])
        if shares is None or shares <= 0:
            continue
        out.append({"line": i, "owner": owner, "role": role, "trade_date": _kr_date(cells[1]),
                    "shares": shares, "price": price, "value": shares * price if price is not None else None,
                    "owned_after": _kr_num(cells[5]), "direct": True, "plan": False})
    return out
