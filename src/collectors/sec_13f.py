"""SEC 13F-HR 보유 보고 (2026-10-25) - 운용사가 분기 말 들고 있던 미국 상장주식(매수 보유만, 분기 끝나고 45일 안 신고).

순수 함수(파싱·합치기·비교)와 SEC/OpenFIGI 호출을 한곳에. 숫자는 신고서 값 그대로 - 점수·순위를 만들지 않는다(원칙 1).

정정 신고(13F-HR/A) 처리:
  - RESTATEMENT: 그 분기 보고를 통째로 바꾼다(가장 늦은 정정본이 기준).
  - NEW HOLDINGS: 원본에 빠졌던 종목을 더한다 - 버크셔가 매집 중이라 비공개 승인을 받았다가 나중에 공개하는 방식이 이것.
가치(value)는 2023년 1월 신고분부터 달러 단위(그 전은 천 달러) - 수집 범위가 그 뒤라 그대로 쓴다.
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET

import requests

from src.collectors.sec_client import SEC_SUBMISSIONS_URL, get

INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"
FILE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{name}"
OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"


def _strip_ns(xml: str) -> ET.Element:
    """13F XML은 네임스페이스가 붙어 있다(informationtable 등) - 태그 이름만 남겨 찾기 쉽게."""
    root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _text(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    f = el.find(path)
    return f.text.strip() if f is not None and f.text else None


def _num(v: str | None) -> float | None:
    if v is None:
        return None
    try:
        return float(v.replace(",", ""))
    except ValueError:
        return None


def list_13f_filings(sub: dict) -> list[dict]:
    """제출 목록(submissions JSON)에서 13F-HR·13F-HR/A만. 13F-NT(보유는 다른 운용사 보고에 포함)는 뺀다."""
    rec = (sub or {}).get("filings", {}).get("recent", {})
    out = []
    for form, acc, filed, period in zip(rec.get("form", []), rec.get("accessionNumber", []),
                                        rec.get("filingDate", []), rec.get("reportDate", [])):
        if form in ("13F-HR", "13F-HR/A"):
            out.append({"form": form, "accession": acc, "filed": filed, "period": period})
    return out


def parse_primary(xml: str) -> dict:
    """primary_doc.xml - 정정 여부·종류, 표 합계(건수·가치)."""
    root = _strip_ns(xml)
    amend = (_text(root, ".//amendmentType") or "").upper() or None
    is_amend = (_text(root, ".//isAmendment") or "").lower() == "true"
    return {"amendment_type": amend if is_amend else None,
            "entries": int(_num(_text(root, ".//tableEntryTotal")) or 0),
            "value_total": _num(_text(root, ".//tableValueTotal"))}


def parse_infotable(xml: str) -> list[dict]:
    """정보표(infoTable 줄마다) -> [{issuer, title, cusip, value, shares, sh_type, put_call}]."""
    root = _strip_ns(xml)
    rows = []
    for t in root.iter("infoTable"):
        cusip = (_text(t, "cusip") or "").upper()
        if not cusip:
            continue
        rows.append({
            "issuer": _text(t, "nameOfIssuer"), "title": _text(t, "titleOfClass"), "cusip": cusip,
            "value": _num(_text(t, "value")), "shares": _num(_text(t, "shrsOrPrnAmt/sshPrnamt")),
            "sh_type": _text(t, "shrsOrPrnAmt/sshPrnamtType"), "put_call": (_text(t, "putCall") or "").upper() or "",
        })
    return rows


def aggregate(rows: list[dict]) -> dict[tuple[str, str], dict]:
    """같은 종목(cusip, 풋/콜)이 운용 주체·의결권별로 여러 줄 - 주식 수·가치를 더한다."""
    out: dict[tuple[str, str], dict] = {}
    for r in rows:
        k = (r["cusip"], r["put_call"])
        cur = out.setdefault(k, {"cusip": r["cusip"], "put_call": r["put_call"], "issuer": r["issuer"], "title": r["title"],
                                 "shares": 0.0, "value": 0.0})
        cur["shares"] += r["shares"] or 0
        cur["value"] += r["value"] or 0
    return out


def is_debt(cusip: str) -> bool:
    """CUSIP 7~8번째(발행 번호)에 글자가 있으면 채권(전환사채 등) - 주식은 숫자. 주식 목록에서 뺀다."""
    issue = (cusip or "")[6:8]
    return len(issue) == 2 and not issue.isdigit()


def value_scale(rows: dict[tuple[str, str], dict]) -> int:
    """가치 단위 판별: 2023년부터 달러가 규칙인데 아직 천 달러로 내는 곳이 있다(실측: 바우포스트·듀케인 - 주당 가치가 0.1~0.5).
    주식 줄의 주당 가치 중앙값이 1달러 미만이면 천 달러로 보고 1000을 곱한다. 판단할 줄이 없으면 1."""
    prices = sorted(v["value"] / v["shares"] for k, v in rows.items()
                    if not k[1] and not is_debt(k[0]) and v.get("shares") and v.get("value"))
    if not prices:
        return 1
    return 1000 if prices[len(prices) // 2] < 1.0 else 1


def normalize_rows(rows: dict[tuple[str, str], dict]) -> dict[tuple[str, str], dict]:
    """저장한 신고 줄 -> 비교용: 가치 단위를 달러로, 채권 줄은 put_call='DEBT'로 따로(화면의 주식 목록에서 빠진다)."""
    scale = value_scale(rows)
    out = {}
    for (cusip, pc), v in rows.items():
        k = (cusip, "DEBT" if not pc and is_debt(cusip) else pc)
        out[k] = {**v, "put_call": k[1], "value": (v["value"] or 0) * scale}
    return out


_SUFFIX = re.compile(r"\b(INC|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|PLC|LLC|LP|NV|N V|SA|AG|HOLDINGS?|HLDGS?|GROUP|GRP|CL [A-C]|CLASS [A-C]|NEW|DEL|THE)\b")


def norm_issuer(name: str | None) -> str:
    """회사명 비교용 - 대문자, 기호·법인 꼬리말 제거. 'Exxon Mobil Corp' == 'EXXON MOBIL CORP'."""
    n = re.sub(r"[^A-Z0-9 ]", " ", (name or "").upper())
    n = _SUFFIX.sub(" ", n)
    return " ".join(n.split())


def merge_renamed(rows: list[dict]) -> list[dict]:
    """같은 분기에 '새로'와 '전량 매도'가 회사명이 같으면 CUSIP만 바뀐 같은 보유(본사 이전·재상장 등, 실측: 엑슨모빌)로 합친다."""
    sold = {norm_issuer(r["issuer"]): r for r in rows if r["status"] == "sold" and not r["put_call"] and norm_issuer(r["issuer"])}
    out, used = [], set()
    for r in rows:
        key = norm_issuer(r["issuer"])
        if r["status"] == "new" and not r["put_call"] and key in sold and key not in used:
            p = sold[key]
            used.add(key)
            chg = (r["shares"] - p["prev_shares"]) / p["prev_shares"] if p["prev_shares"] else None
            status = None if chg is None else "added" if chg > 0.001 else "reduced" if chg < -0.001 else "same"
            out.append({**r, "prev_shares": p["prev_shares"], "prev_value": p.get("prev_value"), "share_chg": chg, "status": status})
        else:
            out.append(r)
    return [r for r in out if not (r["status"] == "sold" and not r["put_call"] and norm_issuer(r["issuer"]) in used)]


def combine_period(filings: list[dict]) -> dict[tuple[str, str], dict]:
    """한 분기의 원본+정정들 -> 그 분기 보유. filings: [{form, filed, amendment_type, rows(aggregate 결과)}].
    신고일 순으로: 원본·RESTATEMENT는 통째로 바꾸고, NEW HOLDINGS는 더한다."""
    pos: dict[tuple[str, str], dict] = {}
    for f in sorted(filings, key=lambda x: (x["filed"], x["form"])):
        if f["form"] == "13F-HR" or f.get("amendment_type") == "RESTATEMENT":
            pos = {k: dict(v) for k, v in f["rows"].items()}
        elif f.get("amendment_type") == "NEW HOLDINGS":
            for k, v in f["rows"].items():
                if k in pos:
                    pos[k]["shares"] += v["shares"]
                    pos[k]["value"] += v["value"]
                else:
                    pos[k] = dict(v)
    return pos


def diff_positions(prev: dict | None, cur: dict) -> list[dict]:
    """직전 분기와 비교 - new(새로) / added(늘림) / reduced(줄임) / same / sold(전량 매도, 이번 분기 0주).
    prev가 None이면(직전 분기 자료 없음) 비교하지 않고 status=None. 주식 수 변화에는 액면분할이 섞일 수 있다."""
    out = []
    for k, v in cur.items():
        p = (prev or {}).get(k)
        if prev is None:
            status, chg = None, None
        elif p is None or not p["shares"]:
            status, chg = "new", None
        else:
            chg = (v["shares"] - p["shares"]) / p["shares"]
            status = "added" if chg > 0.001 else "reduced" if chg < -0.001 else "same"
        out.append({**v, "prev_shares": p["shares"] if p else None, "prev_value": p["value"] if p else None, "share_chg": chg, "status": status})
    if prev is not None:
        for k, p in prev.items():
            if k not in cur and p["shares"]:
                out.append({**p, "shares": 0.0, "value": 0.0, "prev_shares": p["shares"], "prev_value": p["value"], "share_chg": -1.0, "status": "sold"})
    return out


def with_weights(rows: list[dict]) -> list[dict]:
    """주식(풋·콜 빼고) 평가액 합계 대비 비중. 옵션 줄은 비중 없음."""
    total = sum(r["value"] for r in rows if not r["put_call"])
    for r in rows:
        r["weight"] = (r["value"] / total) if total and not r["put_call"] else None
    return rows


# ── SEC 호출 ───────────────────────────────────────────────────────────────

def submissions(s: requests.Session, cik: int) -> dict | None:
    return get(s, SEC_SUBMISSIONS_URL.format(cik=cik))


def fetch_filing(s: requests.Session, cik: int, accession: str) -> dict | None:
    """신고 하나 -> {amendment_type, entries, value_total, rows(aggregate)}. 정보표 파일 이름은 신고마다 달라서 목록에서 찾는다."""
    acc = accession.replace("-", "")
    idx = get(s, INDEX_URL.format(cik=cik, acc=acc))
    names = [it.get("name", "") for it in (idx or {}).get("directory", {}).get("item", [])]
    xmls = [n for n in names if n.lower().endswith(".xml")]
    primary = next((n for n in xmls if n.lower() == "primary_doc.xml"), None)
    others = [n for n in xmls if n != primary]
    if not primary or not others:
        return None
    head = parse_primary(get(s, FILE_URL.format(cik=cik, acc=acc, name=primary), as_json=False) or "<x/>")
    rows: list[dict] = []
    for n in others:   # 보통 하나(정보표). 여럿이면 infoTable이 든 것만 쓰인다
        txt = get(s, FILE_URL.format(cik=cik, acc=acc, name=n), as_json=False) or ""
        if "infoTable" in txt:
            rows += parse_infotable(txt)
    return {**head, "rows": aggregate(rows)}


# ── CUSIP -> 티커 (OpenFIGI, 무료·키 없이 분당 25회·한 번에 10개) ─────────────

def _pick_figi(data: list[dict]) -> dict | None:
    """같은 CUSIP에 여러 줄 - 미국 거래소 보통주·ADR 먼저."""
    if not data:
        return None
    def rank(d: dict) -> int:
        st = (d.get("securityType") or "") + " " + (d.get("securityType2") or "")
        return 0 if "Common Stock" in st else 1 if "Depositary" in st or "ADR" in st else 2
    return sorted(data, key=rank)[0]


def norm_ticker(t: str | None) -> str | None:
    """OpenFIGI 'BRK/B' -> 'BRK.B'(유니버스 표기)."""
    return t.replace("/", ".").upper() if t else None


def _figi_call(body: list[dict], headers: dict, log) -> list | None:
    for attempt in range(5):
        try:
            r = requests.post(OPENFIGI_URL, json=body, headers=headers, timeout=60)
            if r.status_code == 429:
                time.sleep(15 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            log(f"OpenFIGI 실패({type(e).__name__}) - {attempt + 1}번째")
            time.sleep(5 * (attempt + 1))
    return None


def map_cusips(cusips: list[str], api_key: str | None = None, log=print) -> dict[str, dict | None]:
    """-> {cusip: {ticker, name, exch, security_type} | None(OpenFIGI가 '없음'이라고 답함)}.
    한 줄씩 오는 오류(요청 한도 등)·응답 실패는 결과에서 빼서 다음 실행에 다시 묻는다(첫 실행에서 25%가 한도 오류로 빠졌다).
    미국 거래소로 못 찾으면 거래소 조건 없이 한 번 더."""
    out: dict[str, dict | None] = {}
    batch, pause = (100, 0.3) if api_key else (10, 3.0)
    headers = {"Content-Type": "application/json", **({"X-OPENFIGI-APIKEY": api_key} if api_key else {})}
    errors = 0
    for exch in ("US", None):
        todo = [c for c in cusips if c not in out] if exch == "US" else [c for c, v in out.items() if v is None]
        for i in range(0, len(todo), batch):
            chunk = todo[i:i + batch]
            body = [{"idType": "ID_CUSIP", "idValue": c, **({"exchCode": exch} if exch else {})} for c in chunk]
            res = _figi_call(body, headers, log)
            if res is None:
                time.sleep(pause)
                continue
            for c, item in zip(chunk, res):
                if item.get("data"):
                    d = _pick_figi(item["data"])
                    out[c] = {"ticker": norm_ticker(d.get("ticker")), "name": d.get("name"), "exch": d.get("exchCode"),
                              "security_type": d.get("securityType")}
                elif "No identifier" in str(item.get("warning", "")):
                    out.setdefault(c, None)
                else:
                    errors += 1
                    if exch == "US":
                        out.pop(c, None)   # 오류 - 다음 실행에 다시
            time.sleep(pause)
    if errors:
        log(f"OpenFIGI 줄 단위 오류 {errors}건 - 다음 실행에 다시 묻는다")
    return out


def name_match(issuers: dict[str, str], sec_titles: dict[str, str]) -> dict[str, str]:
    """OpenFIGI가 못 찾은 주식 CUSIP -> SEC 회사 목록(company_tickers.json)과 회사명이 정확히 같으면 그 티커.
    issuers: {cusip: 회사명}, sec_titles: {정규화 회사명: 티커}. 이름이 겹치는 회사는 SEC 목록에서 먼저 뺀다(호출하는 쪽)."""
    return {c: sec_titles[norm_issuer(n)] for c, n in issuers.items() if norm_issuer(n) in sec_titles}


def quarter_label(period: str) -> str:
    """'2026-06-30' -> '2026 Q2'."""
    m = re.match(r"(\d{4})-(\d{2})", period or "")
    return f"{m.group(1)} Q{(int(m.group(2)) - 1) // 3 + 1}" if m else period
