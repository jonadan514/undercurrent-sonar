"""한국 상장사의 지난 1년 잠정실적 공시 날짜를 모은다 (2026-11-13).

왜: 일정 화면에서 한국 종목은 실적 발표일이 349곳 중 47곳만 있다 - 한국 회사는 발표일을 미리 공지하는 일이 드물고
yfinance에도 없다. 잠정실적(공정공시)을 내는 회사는 대개 해마다 비슷한 때에 낸다. 작년 같은 분기에 낸 날짜를
52주(같은 요일) 뒤로 옮겨 "예상(작년 기준)"으로 보여 주려고, 그 날짜 이력을 모은다(collect_earnings_calendar가 읽는다).

DART 공시 검색(기업 지정 없이 3개월 창)으로 공정공시(I002) 중 제목에 '잠정'과 '실적'이 든 것만. 정정 공시는 뺀다.
결과: data/kr_prelim_dates.json {종목코드: ["YYYY-MM-DD", ...]} - 저장소에 커밋(Collect DART mode=prelim-history).

    python scripts/fetch_kr_prelim_history.py            # 오늘부터 400일 전까지
    python scripts/fetch_kr_prelim_history.py --days 120
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from collectors import dart_client as dart  # noqa: E402

OUT = ROOT / "data" / "kr_prelim_dates.json"
WINDOW = 30   # DART 기업 지정 없는 검색은 3개월까지 - 1~3월은 공정공시가 많아 85일 창이 2만 건(200쪽) 상한에 잘렸다(11/13)
MAX_PAGES = 200


def is_prelim(report_nm: str) -> bool:
    """'연결재무제표기준영업(잠정)실적(공정공시)', '영업(잠정)실적(공정공시)' 등. 정정·자회사 공시는 뺀다."""
    nm = report_nm or ""
    return "잠정" in nm and "실적" in nm and "정정" not in nm and "자회사" not in nm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--start", default=None, help="YYYY-MM-DD - 이 구간만 다시(잘린 창 채우기)")
    ap.add_argument("--end", default=None)
    args = ap.parse_args()
    have: dict[str, set[str]] = {}
    if OUT.exists():
        have = {k: set(v) for k, v in json.loads(OUT.read_text(encoding="utf-8")).items()}
    end = date.fromisoformat(args.end) if args.end else date.today()
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=args.days)
    cur = start
    total = 0
    while cur <= end:
        stop = min(cur + timedelta(days=WINDOW), end)
        rows = dart.list_disclosures(cur.strftime("%Y%m%d"), stop.strftime("%Y%m%d"), "I", max_pages=MAX_PAGES, pblntf_detail_ty="I002")
        if len(rows) >= MAX_PAGES * 100:
            print(f"[prelim-hist] 경고: {cur} ~ {stop} 상한({MAX_PAGES * 100}건)에 닿음 - 창을 더 줄여야 한다", flush=True)
        hit = [r for r in rows if r.get("stock_code") and is_prelim(r.get("report_nm", ""))]
        for r in hit:
            d = str(r["rcept_dt"])
            have.setdefault(r["stock_code"], set()).add(f"{d[:4]}-{d[4:6]}-{d[6:8]}")
        total += len(hit)
        print(f"[prelim-hist] {cur} ~ {stop}: 공정공시 {len(rows)}건 중 잠정실적 {len(hit)}건", flush=True)
        cur = stop + timedelta(days=1)
    OUT.write_text(json.dumps({k: sorted(v) for k, v in sorted(have.items())}, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"[prelim-hist] 저장 {len(have)}종목 (이번 실행 {total}건)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
