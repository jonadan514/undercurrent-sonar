"""한국 공시 알림 - 공급계약·잠정실적·결산실적 공시예고 (2026-10-17, 사용자 결정).

DART 거래소공시 목록(list.json, pblntf_ty=I)에서 세 종류만 골라 원문 표(dart_client.document_rows)를 읽는다.
원문 표는 '항목 | 값' 행이라 항목 이름 옆 값을 그대로 옮긴다 - 숫자는 공시 값 그대로이고 만들지 않는다(원칙 2).
못 읽은 칸은 None으로 둔다(원칙 5 - 결측은 정상).

  contract  단일판매ㆍ공급계약체결 - 계약금액(원), 매출액 대비(%), 계약 내용·상대·기간
            자회사 공시("자회사의 주요경영사항")는 뺀다 - 매출 대비가 자회사 매출 기준이라 본사 기준으로 읽히면 안 된다.
  prelim    (연결재무제표기준)영업(잠정)실적(공정공시) - 매출·영업이익·순이익 당해 분기와 전년동기 대비(%)
            회사가 적은 증감율이 같은 표의 두 값과 1%p 넘게 어긋나면 그 증감율은 버린다(칸 위치가 다른 양식 대비).
  notice    결산실적공시예고 - 결산실적 공시 예정일(한국 실적 발표 일정, yfinance 빈칸 보완)
정정공시([기재정정] 등)는 원 공시를 고친 것이라 새 알림으로 세지 않는다.
"""
from __future__ import annotations

import re

KIND_PATTERNS = (
    ("contract", re.compile(r"단일판매\s*[ㆍ·]?\s*공급계약체결")),
    ("prelim", re.compile(r"영업\s*\(\s*잠정\s*\)\s*실적")),
    ("notice", re.compile(r"결산실적공시\s*예고")),
)
UNIT = {"원": 1, "천원": 1e3, "백만원": 1e6, "억원": 1e8}
_NUM_RE = re.compile(r"^\(?-?[\d,]+(?:\.\d+)?\)?$")
_DATE_RE = re.compile(r"(\d{4})[-.](\d{2})[-.](\d{2})")


def classify(report_nm: str) -> str | None:
    """공시 제목 -> 'contract' | 'prelim' | 'notice' | None. 정정공시·자회사 공시는 None."""
    nm = report_nm or ""
    if "정정" in nm or "자회사" in nm or "종속회사" in nm:
        return None
    for kind, pat in KIND_PATTERNS:
        if pat.search(nm):
            return kind
    return None


def num(s: str | None) -> float | None:
    """'1,908,000,000' -> 1908000000.0, '(7,650)' 또는 '-7,650' -> -7650.0, '-'·빈칸 -> None."""
    if s is None:
        return None
    t = s.strip()
    if not t or not _NUM_RE.match(t):
        return None
    neg = t.startswith("(") and t.endswith(")")
    v = float(t.strip("()").replace(",", ""))
    return -v if neg else v


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.split("|")]


def _after(rows: list[str], label: re.Pattern, *, skip_dash_prefix: bool = False) -> str | None:
    """label에 맞는 칸 바로 다음 칸 값(첫 행)."""
    for row in rows:
        cells = _cells(row)
        for i, c in enumerate(cells[:-1]):
            if skip_dash_prefix and c.startswith("-"):
                continue
            if label.search(c):
                return cells[i + 1] or None
    return None


def _date(s: str | None) -> str | None:
    m = _DATE_RE.search(s or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def parse_contract(rows: list[str]) -> dict:
    amount = num(_after(rows, re.compile(r"계약금액\s*총액\s*\(원\)")))
    if amount is None:
        amount = num(_after(rows, re.compile(r"^(?:\d+\.\s*계약내역\s*)?계약금액\s*\(원\)$")))
    if amount is None:
        amount = num(_after(rows, re.compile(r"계약금액\s*\(원\)")))
    return {
        "title": _after(rows, re.compile(r"판매\s*[ㆍ·]?\s*공급계약\s*내용|체결계약명")),
        "amount": amount,
        # 계약상대방의 최근 매출액("- 최근 매출액")은 건너뛴다 - 첫 번째가 공시 회사 것
        "recent_revenue": num(_after(rows, re.compile(r"최근\s*매출액\s*\(원\)"), skip_dash_prefix=True)),
        "pct_of_revenue": num(_after(rows, re.compile(r"매출액\s*대비\s*\(%\)"))),
        "counterparty": _after(rows, re.compile(r"계약상대(?:방)?$|^\d+\.\s*계약상대(?:방)?$")),
        "start": _date(_after(rows, re.compile(r"시작일"))),
        "end": _date(_after(rows, re.compile(r"종료일"))),
    }


_ROW_LABELS = {
    "revenue": re.compile(r"^(매출액|영업수익|수익\(매출액\)|매출)"),
    "operating_income": re.compile(r"^영업이익"),
    "net_income": re.compile(r"^당기순이익"),
}


def _yoy_ok(cur: float | None, base: float | None, pct: float | None) -> bool:
    """회사가 적은 증감율이 두 값과 맞는지(1%p 안). 확인할 수 없으면(값 없음·전년 0 이하) 쓰지 않는다."""
    if cur is None or base is None or pct is None or base <= 0:
        return False
    return abs((cur / base - 1) * 100 - pct) <= 1.0


def parse_prelim(rows: list[str]) -> dict:
    unit = None
    for row in rows:
        m = re.search(r"단위\s*:\s*(백만원|억원|천원|원)", row)
        if m:
            unit = UNIT[m.group(1)]
            break
    period_end = None
    for row in rows:
        cells = _cells(row)
        if cells and cells[0].startswith("당기실적") and len(cells) >= 4:
            period_end = _date(cells[-1])
            break
    out: dict = {"unit": unit, "period_end": period_end}
    for key, pat in _ROW_LABELS.items():
        out[key] = out[f"{key}_yoy_base"] = out[f"{key}_yoy_pct"] = out[f"{key}_yoy_turn"] = None
        for row in rows:
            cells = _cells(row)
            if not cells or not pat.search(cells[0]) or "당해실적" not in cells:
                continue
            vals = cells[cells.index("당해실적") + 1:]
            if len(vals) < 7 or unit is None:
                break
            cur, base, pct = num(vals[0]), num(vals[4]), num(vals[5])
            turn = vals[6] if vals[6] and vals[6] != "-" else None
            out[key] = cur * unit if cur is not None else None
            out[f"{key}_yoy_base"] = base * unit if base is not None else None
            out[f"{key}_yoy_pct"] = pct if _yoy_ok(cur, base, pct) else None
            out[f"{key}_yoy_turn"] = turn
            break
    return out


def parse_notice(rows: list[str]) -> dict:
    start = end = None
    for row in rows:
        cells = _cells(row)
        if "시작일" in cells and start is None:
            start = _date(cells[cells.index("시작일") + 1] if cells.index("시작일") + 1 < len(cells) else None)
        if "종료일" in cells and end is None:
            end = _date(cells[cells.index("종료일") + 1] if cells.index("종료일") + 1 < len(cells) else None)
    return {"announce_date": _date(_after(rows, re.compile(r"결산실적\s*공시\s*예정일"))),
            "period_start": start, "period_end": end}


PARSERS = {"contract": parse_contract, "prelim": parse_prelim, "notice": parse_notice}


# ── 표시 (일일 알림·주간 브리핑 공용) ──────────────────────────────

DART_VIEW = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"


def fmt_eok(v: float | None) -> str:
    """원 -> '19억' / '1.2조'. 1억 미만은 '0.5억'."""
    if v is None:
        return "-"
    if abs(v) >= 1e12:
        return f"{v / 1e12:.1f}조"
    if abs(v) >= 1e8:
        return f"{v / 1e8:,.0f}억"
    return f"{v / 1e8:.1f}억"


def _yoy(p: dict, key: str) -> str | None:
    if p.get(f"{key}_yoy_turn"):
        return p[f"{key}_yoy_turn"]
    pct = p.get(f"{key}_yoy_pct")
    return None if pct is None else f"{pct:+.0f}%"


def quarter_label(period_end: str | None) -> str:
    """'2026-09-30' -> '26.3Q'(분기말 달 기준). 없으면 ''."""
    if not period_end:
        return ""
    y, m = int(period_end[:4]), int(period_end[5:7])
    return f"{y % 100}.{(m - 1) // 3 + 1}Q"


def summary(kind: str, p: dict) -> str:
    """한 줄 요약(태그 없는 평문). 숫자는 파싱한 공시 값 그대로."""
    if kind == "contract":
        pct = f" (매출 대비 {p['pct_of_revenue']:.1f}%)" if p.get("pct_of_revenue") is not None else ""
        title = f" · {p['title'][:30]}" if p.get("title") else ""
        return f"공급계약 {fmt_eok(p.get('amount'))}{pct}{title}"
    if kind == "prelim":
        parts = [f"{name} {v}" for name, key in (("매출", "revenue"), ("영업익", "operating_income"))
                 if (v := _yoy(p, key))]
        q = quarter_label(p.get("period_end"))
        return f"잠정실적 {q}".rstrip() + (f" 전년동기 대비 {' · '.join(parts)}" if parts else "")
    if kind == "notice":
        return f"실적 발표 예정 {p.get('announce_date') or '-'}"
    return kind
