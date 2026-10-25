"""13F 수집 점검(읽기 전용, 2026-10-25) - 운용사별 최근 신고의 표 합계와 저장한 줄 합계, 상위 종목 가치·주식 수·주당 가치.
가치 단위(달러/천 달러)·파싱 오류를 눈으로 확인하는 용도.

    python scripts/report_13f.py [--managers berkshire baupost]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db.data_store import get_db  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--managers", nargs="*", default=None)
    args = ap.parse_args()
    conn = get_db()
    fl = conn.execute("SELECT manager_id, accession, form, period, filed_on, amendment_type, entries, value_total FROM inst_13f_filings "
                      "ORDER BY manager_id, period DESC, filed_on DESC").fetchall()
    shown = set()
    for mid, acc, form, period, filed, amend, entries, vt in fl:
        if args.managers and mid not in args.managers:
            continue
        if (mid, period) in shown and len([1 for x in shown if x[0] == mid]) >= 2:
            continue
        shown.add((mid, period))
        rows = conn.execute("SELECT issuer, cusip, put_call, shares, value FROM inst_13f_rows WHERE accession = ? ORDER BY value DESC", (acc,)).fetchall()
        total = sum(float(r[4] or 0) for r in rows)
        print(f"## {mid} {period} {form} {amend or ''} filed {filed}: 표 합계 {vt} · 저장 줄 합 {total:,.0f} · 줄 {len(rows)} (신고 {entries})")
        for issuer, cusip, pc, sh, v in rows[:4]:
            sh, v = float(sh or 0), float(v or 0)
            print(f"   {issuer} {cusip} {pc or ''} 주식 {sh:,.0f} · 가치 {v:,.0f} · 주당 {v / sh if sh else 0:,.2f}")
        nulls = sum(1 for r in rows if r[4] is None or float(r[4] or 0) == 0)
        if nulls:
            print(f"   가치 0·없음 {nulls}줄")
    unm = conn.execute("SELECT COUNT(*) FROM cusip_map WHERE ticker IS NULL").fetchone()[0]
    print(f"\nCUSIP 못 찾음 {unm} - 예: {[r for r in conn.execute('SELECT c.cusip, (SELECT issuer FROM inst_13f_rows r WHERE r.cusip = c.cusip LIMIT 1) FROM cusip_map c WHERE c.ticker IS NULL LIMIT 15').fetchall()]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
