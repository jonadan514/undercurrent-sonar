"""DART OpenAPI 호출 (분기 재설계 docs/REDESIGN_SPEC.md 4-1).

키는 환경변수 DART_API_KEY로만 받는다. 코드·저장소·로그에 키를 남기지 않는다.

쓰는 API
  corpCode.xml        전체 기업 고유번호 zip. 종목코드(6자리) -> 기업코드(8자리) 매핑
  company.json        기업개황(업종코드 등)
  list.json           공시 검색 - 최근 사업보고서 접수번호 찾기
  document.xml        공시 원문 zip - 사업보고서의 "사업의 개요" 텍스트 추출
  fnlttSinglAcnt.json 단일회사 주요계정 - 매출액·영업이익·당기순이익

DART 상태 코드: 000 정상 / 013 조회된 데이터 없음 / 020 요청 제한 초과 / 800 점검 /
010·011 키 오류. 013은 오류가 아니라 "그 보고서가 없다"는 뜻이라 빈 결과로 돌려준다.
"""
from __future__ import annotations

import io
import json
import os
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE = "https://opendart.fss.or.kr/api"
MAX_ATTEMPTS = 5
NO_DATA = ("013", "014")   # 013 조회된 데이터 없음 / 014 파일이 존재하지 않습니다
RETRY_STATUSES = {"020", "800", "900"}


class DartKeyError(RuntimeError):
    """키가 없거나 잘못됐다 - 재시도해도 소용없으니 즉시 멈춘다."""


def api_key() -> str:
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        raise DartKeyError("DART_API_KEY 환경변수가 없다 (GitHub Actions는 Secrets에 등록)")
    return key


def _get(path: str, params: dict, *, binary: bool = False):
    """재시도 포함 GET. binary면 bytes, 아니면 파싱된 JSON."""
    params = {"crtfc_key": api_key(), **params}
    last = ""
    for attempt in range(MAX_ATTEMPTS):
        try:
            r = requests.get(f"{BASE}/{path}", params=params, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}"
                time.sleep(min(2 ** (attempt + 1), 30))
                continue
            r.raise_for_status()
            if binary:
                # 오류일 때는 zip 대신 JSON/XML 오류 메시지가 온다
                if r.content[:2] != b"PK":
                    msg = r.content[:300].decode("utf-8", errors="replace")
                    if "010" in msg or "011" in msg:
                        raise DartKeyError("DART 키가 유효하지 않다")
                    if any(f"<status>{code}</status>" in msg or code in msg for code in NO_DATA):
                        return None
                    last = msg
                    time.sleep(min(2 ** (attempt + 1), 30))
                    continue
                return r.content
            try:
                data = r.json()
            except ValueError:
                # 2026-10-11 정기 실행: 121종목 전부 JSONDecodeError - 점검 안내 같은 비JSON 응답으로 보인다.
                # 재시도하고, 끝내 안 되면 응답 앞부분을 남겨 원인을 볼 수 있게 한다.
                snippet = " ".join(r.text[:200].split())
                last = f"비JSON 응답(HTTP {r.status_code}, {r.headers.get('content-type', '')}): {snippet}"
                time.sleep(min(2 ** (attempt + 1), 30))
                continue
            status = str(data.get("status", ""))
            if status == "000":
                return data
            if status in NO_DATA:
                return {"status": status, "list": []}
            if status in ("010", "011", "012"):
                raise DartKeyError(f"DART 키 오류 status={status}")
            if status in RETRY_STATUSES:
                last = f"status={status} {data.get('message', '')}"
                time.sleep(min(2 ** (attempt + 2), 60))
                continue
            raise RuntimeError(f"DART 오류 status={status} {data.get('message', '')}")
        except (requests.Timeout, requests.ConnectionError) as e:
            last = type(e).__name__
            time.sleep(min(2 ** (attempt + 1), 30))
    raise RuntimeError(f"DART 호출 실패 {path}: {last}")


# ── 기업코드 매핑 ──────────────────────────────────────────────

def meta_path(cache: Path) -> Path:
    """캐시 파일 옆의 메타 파일 경로. data/dart_corp_codes.json -> data/dart_corp_codes_meta.json"""
    return cache.with_name(f"{cache.stem}_meta{cache.suffix}")


def _cache_fetched_at(cache: Path) -> datetime | None:
    """메타 파일에 적힌 수집 시각. 없거나 깨져 있으면 None(= 오래된 것으로 본다)."""
    try:
        raw = json.loads(meta_path(cache).read_text(encoding="utf-8"))["fetched_at"]
        ts = datetime.fromisoformat(raw)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def load_corp_codes(cache: Path, max_age_days: int = 30) -> dict[str, str]:
    """{종목코드: 기업코드}. 메타 파일의 수집 시각이 max_age_days 이내면 다운로드하지 않는다.

    신선도를 파일 mtime으로 판단하지 않는다(2026-09-21 수정). 이 캐시는 저장소에 커밋되고
    GitHub Actions가 매번 새로 checkout하므로 mtime은 늘 "방금"이라, 캐시가 영원히 갱신되지
    않고 신규 상장 종목이 계속 빠졌다. 메타 파일이 없거나 깨져 있으면 오래된 것으로 보고 한 번
    새로 받는다. 캐시 파일 형식({종목코드: 기업코드})은 그대로다.
    """
    fetched = _cache_fetched_at(cache)
    if cache.exists() and fetched and (datetime.now(timezone.utc) - fetched) < timedelta(days=max_age_days):
        return json.loads(cache.read_text(encoding="utf-8"))

    # 다운로드에 실패하면 예외가 그대로 올라가고 기존 캐시 파일은 건드리지 않는다.
    raw = _get("corpCode.xml", {}, binary=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        xml_bytes = zf.read(zf.namelist()[0])
    root = ET.fromstring(xml_bytes)
    mapping: dict[str, str] = {}
    for item in root.iter("list"):
        stock = (item.findtext("stock_code") or "").strip()
        corp = (item.findtext("corp_code") or "").strip()
        if stock and corp:
            mapping[stock] = corp
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(mapping, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    meta_path(cache).write_text(
        json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "count": len(mapping)}),
        encoding="utf-8")
    return mapping


# ── 재무 ──────────────────────────────────────────────────────

def fetch_key_accounts(corp_code: str, year: int, reprt_code: str) -> list[dict]:
    """단일회사 주요계정. 보고서가 없으면 빈 목록."""
    data = _get("fnlttSinglAcnt.json",
                {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": reprt_code})
    return list(data.get("list") or [])


# ── 기업개황·사업의 개요 ──────────────────────────────────────

def fetch_company(corp_code: str) -> dict:
    data = _get("company.json", {"corp_code": corp_code})
    return data if data.get("status") == "000" else {}


def latest_annual_report_no(corp_code: str, bgn_de: str, end_de: str) -> str | None:
    """기간 안에서 가장 최근 사업보고서(A001) 접수번호. 없으면 None."""
    data = _get("list.json", {"corp_code": corp_code, "bgn_de": bgn_de, "end_de": end_de,
                              "pblntf_detail_ty": "A001", "page_count": "10"})
    items = [i for i in (data.get("list") or []) if "사업보고서" in (i.get("report_nm") or "")]
    if not items:
        return None
    items.sort(key=lambda i: i.get("rcept_dt", ""), reverse=True)
    return items[0].get("rcept_no")


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
# 공시 원문은 회사·연도마다 인코딩이 다르다(최근은 utf-8, 예전 양식은 EUC-KR 계열).
# utf-8로만 읽으면 한글이 깨져 제목 검색이 전부 실패한다 - 2026-09-18에 5종목 중 3종목이
# "사업의 개요 못 찾음"으로 나온 원인이었다.
DOC_ENCODINGS = ("utf-8", "cp949", "euc-kr")
# 구간 시작·끝 제목. 번호 표기가 "1.", "1)", "가." 등으로 회사마다 다르다.
_START_PATTERNS = (r"사업의\s*개요", r"Ⅱ\s*[.．]?\s*사업의\s*내용", r"II\s*[.．]?\s*사업의\s*내용")
_END_PATTERNS = (r"주요\s*제품\s*및\s*서비스", r"주요\s*제품\s*및\s*원재료", r"2\s*[.．)]\s*주요",
                 r"원재료\s*및\s*생산설비", r"매출\s*및\s*수주상황")


def _decode(data: bytes) -> str:
    for enc in DOC_ENCODINGS:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_overview(plain: str, max_chars: int) -> str | None:
    """태그를 걷어낸 텍스트에서 '사업의 개요' 본문 중 가장 실한 구간을 고른다.

    같은 제목이 목차에도 나오기 때문에 첫 번째를 쓰면 목차 몇 글자만 잡힌다.
    모든 등장 위치를 보고 뒤따르는 본문이 가장 긴 것을 쓴다.
    """
    best = None
    for pat in _START_PATTERNS:
        for m in re.finditer(pat, plain):
            # 상호참조("...'1. 사업의 개요'를 참조하시기 바랍니다")는 본문이 아니다.
            # 참조 문구는 제목 앞에도("아래 1. 사업의 개요 참고") 뒤에도 올 수 있어 양쪽을 본다.
            before = plain[max(0, m.start() - 25):m.start()]
            after = plain[m.end():m.end() + 25]
            if re.search(r"참조|참고|기재", before) or re.search(r"참조|참고", after):
                continue
            rest = plain[m.end():m.end() + 20000]
            end = None
            for ep in _END_PATTERNS:
                found = re.search(ep, rest)
                if found and (end is None or found.start() < end):
                    end = found.start()
            if end is None:
                continue  # 다음 절 제목이 안 나오면 목차나 상호참조다 - 본문은 반드시 닫힌다
            body = rest[:end].strip()
            if len(body) >= 200 and (best is None or len(body) > len(best)):
                best = body
    return best[:max_chars] if best else None


def business_overview(rcept_no: str, max_chars: int = 2500) -> str | None:
    """사업보고서 원문에서 'II. 사업의 내용'의 '사업의 개요' 본문을 뽑는다.

    원문 zip 안의 모든 파일을 훑는다 - 본문이 가장 큰 파일이 아닐 수 있고(첨부·감사보고서가
    더 큰 경우가 있다), 회사마다 파일을 쪼개는 방식이 다르다. 못 찾으면 None.
    """
    raw = _get("document.xml", {"rcept_no": rcept_no}, binary=True)
    if not raw:
        return None
    best = None
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for name in sorted(zf.namelist(), key=lambda n: -zf.getinfo(n).file_size):
            plain = _SPACE_RE.sub(" ", _TAG_RE.sub(" ", _decode(zf.read(name))))
            got = _extract_overview(plain, max_chars)
            if got and (best is None or len(got) > len(best)):
                best = got
    return best


# ── 공시 목록·원문 표 (2026-10-17, 공급계약·잠정실적 알림) ─────────────

def list_disclosures(bgn_de: str, end_de: str, pblntf_ty: str = "I", max_pages: int = 40) -> list[dict]:
    """기간 안의 전체 공시 목록(기업 지정 없음 - DART는 이때 기간 3개월까지). pblntf_ty I = 거래소공시.
    항목: corp_code, corp_name, stock_code, corp_cls(Y 코스피/K 코스닥), report_nm, rcept_no, rcept_dt."""
    out: list[dict] = []
    page = 1
    while page <= max_pages:
        data = _get("list.json", {"bgn_de": bgn_de, "end_de": end_de, "pblntf_ty": pblntf_ty,
                                  "page_no": str(page), "page_count": "100"})
        out.extend(data.get("list") or [])
        total_page = int(data.get("total_page") or 1)
        if page >= total_page:
            break
        page += 1
    return out


_STYLE_RE = re.compile(r"<\s*(style|script)[^>]*>.*?<\s*/\s*\1\s*>", re.I | re.S)
_ROW_END_RE = re.compile(r"</\s*TR\s*>", re.I)
_CELL_END_RE = re.compile(r"</\s*T[DHEU]\s*>", re.I)   # DART 문서는 TD 외에 TE·TU 칸도 쓴다


def document_rows(rcept_no: str) -> list[str]:
    """공시 원문을 표 행 단위 텍스트로. 칸은 ' | '로 잇는다(표 구조를 남겨 항목 이름 옆 값을 찾게).
    원문이 없으면 빈 목록."""
    raw = _get("document.xml", {"rcept_no": rcept_no}, binary=True)
    if not raw:
        return []
    rows: list[str] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for name in zf.namelist():
            text = _STYLE_RE.sub(" ", _decode(zf.read(name)))
            text = re.sub(r"[\r\n]+", " ", text)   # 원문 줄바꿈은 의미 없다 - 행 구분은 </TR>로만
            text = _CELL_END_RE.sub(" | ", text)
            text = _ROW_END_RE.sub("\n", text)
            for line in _TAG_RE.sub(" ", text).split("\n"):
                line = re.sub(r"[ \t\xa0]+", " ", line).strip(" |")
                if line:
                    rows.append(line)
    return rows


# ── 웹 뷰어 원문 (2026-10-21) - 개인이 내는 지분 보고서(임원ㆍ주요주주 소유상황)는 document.xml이 없다 ──
VIEWER_MAIN = "https://dart.fss.or.kr/dsaf001/main.do"
VIEWER_DOC = "https://dart.fss.or.kr/report/viewer.do"
_DCM_RE = re.compile(r"node\d*\['dcmNo'\]\s*=\s*\"(\d+)\"|dcmNo['\"]?\s*[:=]\s*['\"](\d+)['\"]")


def viewer_rows(rcept_no: str) -> list[str]:
    """DART 웹 뷰어에서 원문 HTML을 받아 document_rows와 같은 '칸 | 칸' 행으로. 못 받으면 빈 목록."""
    headers = {"User-Agent": "Mozilla/5.0 (U-Sonar research)"}
    try:
        page = requests.get(VIEWER_MAIN, params={"rcpNo": rcept_no}, headers=headers, timeout=30).text
        m = _DCM_RE.search(page)
        if not m:
            return []
        dcm = m.group(1) or m.group(2)
        html = requests.get(VIEWER_DOC, params={"rcpNo": rcept_no, "dcmNo": dcm, "eleId": "0", "offset": "0",
                                                "length": "0", "dtd": "HTML"}, headers=headers, timeout=30).text
    except (requests.Timeout, requests.ConnectionError):
        return []
    text = _STYLE_RE.sub(" ", html)
    text = re.sub(r"[\r\n]+", " ", text)
    text = _CELL_END_RE.sub(" | ", text)
    text = _ROW_END_RE.sub("\n", text)
    rows = []
    for line in _TAG_RE.sub(" ", text).split("\n"):
        line = re.sub(r"[ \t\xa0]+", " ", line).replace("&nbsp;", " ").strip(" |")
        if line:
            rows.append(line)
    return rows
