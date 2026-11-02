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


def latest_quarter_status(conn, managers: list[str] | None) -> None:
    """운용사마다 가장 최근 분기(화면이 보는 분기): 보유 주식 수, 티커를 못 찾은 보유(수·평가액 비중), 새로 산 종목의 비중 분포.
    11/14 3분기 신고 전후로 '못 찾은 티커 비율'과 확신 매수 기준(3%)을 보려고(2026-11-02)."""
    print("\n== 가장 최근 분기 (화면 기준) ==")
    rows = conn.execute(
        "SELECT p.manager_id, p.period, p.ticker, p.value, p.weight, p.status FROM inst_13f_positions p "
        "JOIN (SELECT manager_id, MAX(period) AS period FROM inst_13f_positions GROUP BY manager_id) m "
        "ON m.manager_id = p.manager_id AND m.period = p.period WHERE p.put_call = ''").fetchall()
    by: dict[str, list] = {}
    for r in rows:
        if managers and r[0] not in managers:
            continue
        by.setdefault(r[0], []).append(r)
    tot_held = tot_unm = 0
    tot_val = tot_unm_val = 0.0
    new_w: list[float] = []
    for mid in sorted(by):
        rs = by[mid]
        held = [r for r in rs if r[5] != "sold"]
        unm = [r for r in held if not r[2]]
        val = sum(float(r[3] or 0) for r in held)
        unm_val = sum(float(r[3] or 0) for r in unm)
        news = [float(r[4] or 0) for r in rs if r[5] == "new"]
        new_w += news
        tot_held += len(held)
        tot_unm += len(unm)
        tot_val += val
        tot_unm_val += unm_val
        print(f"  {mid:11s} {rs[0][1]} 보유 {len(held):4d} · 티커 없음 {len(unm):3d} (평가액 {unm_val / val * 100 if val else 0:4.1f}%) · "
              f"새로 {len(news):3d} (비중 3%+ {sum(1 for w in news if w >= 0.03)})")
    if tot_held:
        print(f"  합계: 보유 {tot_held} · 티커 없음 {tot_unm} ({tot_unm / tot_held * 100:.1f}%, 평가액 {tot_unm_val / tot_val * 100 if tot_val else 0:.1f}%)")
    if new_w:
        print("  새로 산 종목 비중 분포: " + ", ".join(f"{t * 100:g}%+ {sum(1 for w in new_w if w >= t)}" for t in (0.005, 0.01, 0.02, 0.03, 0.05, 0.1))
              + f" (전체 {len(new_w)})")


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
    latest_quarter_status(conn, args.managers)
    unm = conn.execute("SELECT COUNT(*) FROM cusip_map WHERE ticker IS NULL").fetchone()[0]
    print(f"\nCUSIP 못 찾음 {unm} - 예: {[r for r in conn.execute('SELECT c.cusip, (SELECT issuer FROM inst_13f_rows r WHERE r.cusip = c.cusip LIMIT 1) FROM cusip_map c WHERE c.ticker IS NULL LIMIT 15').fetchall()]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
