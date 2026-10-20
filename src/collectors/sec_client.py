"""SEC EDGAR 공통 호출 (2026-10-21) - 내부자 매수(Form 4)·8-K 수집이 같이 쓴다.

SEC는 User-Agent에 연락처 필수(SEC_USER_AGENT, GitHub Secrets - 코드·로그에 남기지 않는다), 초당 10회 한도 -> 호출 사이 0.15초.
"""
from __future__ import annotations

import os
import time

import requests

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
SEC_SLEEP = 0.15


def session() -> requests.Session:
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua:
        raise SystemExit("SEC_USER_AGENT 환경변수가 없다 (GitHub Secrets)")
    s = requests.Session()
    s.headers.update({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
    return s


def get(s: requests.Session, url: str, as_json: bool = True):
    for attempt in range(4):
        try:
            r = s.get(url, timeout=60)
            if r.status_code == 404:
                return None
            if r.status_code in (403, 429) or r.status_code >= 500:
                time.sleep(2 ** (attempt + 1))
                continue
            r.raise_for_status()
            return r.json() if as_json else r.text
        except (requests.Timeout, requests.ConnectionError, ValueError):
            time.sleep(2 ** (attempt + 1))
        finally:
            time.sleep(SEC_SLEEP)
    raise RuntimeError(f"SEC 호출 실패 {url}")


def ticker_ciks(s: requests.Session) -> dict[str, int]:
    return {str(v["ticker"]).upper(): int(v["cik_str"]) for v in (get(s, SEC_TICKERS_URL) or {}).values()}


def cik_for(ciks: dict[str, int], ticker: str) -> int | None:
    """BRK.B 같은 점 표기는 SEC 목록에서 BRK-B."""
    return ciks.get(ticker.upper()) or ciks.get(ticker.upper().replace(".", "-"))


def doc_url(cik: int, accession: str, doc: str) -> str:
    return SEC_DOC_URL.format(cik=cik, acc=accession.replace("-", ""), doc=doc)
