"""13F 운용사 CIK 확인(읽기 전용, 2026-10-25). config/institutions.yaml의 cik로 EDGAR 제출 목록을 열어 이름·최근 13F-HR을 보이고,
이름 검색(search)으로 13F를 내는 다른 후보도 같이 보인다 - 사람이 보고 cik를 고정한다.

    SEC_USER_AGENT=... python scripts/probe_13f_filers.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.collectors.sec_client import SEC_SUBMISSIONS_URL, get, session  # noqa: E402

SEARCH_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={q}&type=13F-HR&dateb=&owner=include&count=10&output=atom"


def latest_13f(sub: dict) -> list[tuple[str, str, str]]:
    rec = sub.get("filings", {}).get("recent", {})
    out = []
    for form, filed, period in zip(rec.get("form", []), rec.get("filingDate", []), rec.get("reportDate", [])):
        if form.startswith("13F-HR"):
            out.append((form, filed, period))
    return out[:3]


def main() -> int:
    s = session()
    for m in yaml.safe_load(open(ROOT / "config" / "institutions.yaml", encoding="utf-8"))["managers"]:
        print(f"## {m['id']} ({m['en']}) cik={m['cik']}")
        sub = get(s, SEC_SUBMISSIONS_URL.format(cik=int(m["cik"]))) if m.get("cik") else None
        if sub:
            print(f"  등록 이름: {sub.get('name')} · 최근 13F: {latest_13f(sub) or '없음'}")
        else:
            print("  CIK로 못 찾음")
        atom = get(s, SEARCH_URL.format(q=m["search"].replace(" ", "+")), as_json=False) or ""
        hits = re.findall(r"<cik>(\d+)</cik>.*?<conformed-name>(.*?)</conformed-name>", atom, re.S) or \
            re.findall(r"CIK=(\d{6,10})[^>]*>[^<]*</a>", atom)
        names = re.findall(r"<title>(.*?)</title>", atom)
        print(f"  이름 검색 '{m['search']}': {hits[:5] if hits else names[:6]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
