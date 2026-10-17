"""SEC companyfacts에서 종목별로 어떤 매출·이익 계정이 분기 값을 갖는지 본다(읽기 전용, 2026-10-17).

collect_us_sec_quarterly.py가 '매출 분기 없음'·'기업번호 없음'으로 건너뛴 종목의 원인 확인용.
    python scripts/inspect_sec_concepts.py APA EWBC FFIN SYF EA
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from collect_us_sec_quarterly import FACTS_URL, TICKERS_URL, _get_json, _session  # noqa: E402
from src.collectors.sec_financials import SINCE, concept_series  # noqa: E402

KEYWORDS = ("Revenue", "Sales", "InterestAndDividendIncome", "InterestIncome", "NoninterestIncome",
            "OperatingIncome", "NetIncome", "ProfitLoss", "IncomeLoss")


def main() -> int:
    s = _session()
    data = _get_json(s, TICKERS_URL) or {}
    by_ticker = {str(v["ticker"]).upper(): v for v in data.values()}
    for t in sys.argv[1:]:
        print(f"\n===== {t} =====")
        v = by_ticker.get(t.upper())
        if not v:
            hits = [x for x in data.values() if t.upper() in str(x["title"]).upper().replace(" ", "")
                    or str(x["ticker"]).upper().startswith(t.upper())][:5]
            print(f"  티커 매핑 없음. 이름·티커 비슷한 것: {[(x['ticker'], x['title'], x['cik_str']) for x in hits]}")
            continue
        print(f"  CIK {v['cik_str']} {v['title']}")
        facts = _get_json(s, FACTS_URL.format(cik=int(v["cik_str"]))) or {}
        for ns, concepts in (facts.get("facts") or {}).items():
            for name, body in concepts.items():
                if not any(k in name for k in KEYWORDS):
                    continue
                items = (body.get("units") or {}).get("USD") or []
                ser = concept_series(items)
                recent = sorted(e for e in ser if e >= SINCE)
                if len(recent) >= 4:
                    last = recent[-1]
                    print(f"  {ns}:{name}  분기 {len(recent)}개, 최근 {last} = {ser[last][0] / 1e6:,.0f}M")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
