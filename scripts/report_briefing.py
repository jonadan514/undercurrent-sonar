"""읽기 전용 - 저장된 주간 브리핑의 칸별 건수·빈 칸 점검 (2026-10-26, 첫 정기 브리핑 점검).

샌드박스에서 DB·사이트에 못 닿아 워크플로로 본다. 숫자·이름만 찍고 값은 바꾸지 않는다.

    python scripts/report_briefing.py            # 가장 최근 주
    python scripts/report_briefing.py --week 2026-10-26
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db.data_store import get_db  # noqa: E402


def size(v) -> str:
    """칸 크기 한 줄: 목록은 건수, 사전은 안쪽 목록 건수, 글은 글자 수, 비면 '비어 있음'."""
    if v is None:
        return "없음(None)"
    if isinstance(v, list):
        return f"{len(v)}건" if v else "비어 있음"
    if isinstance(v, str):
        return f"글 {len(v)}자" if v.strip() else "비어 있음"
    if isinstance(v, dict):
        parts = [f"{k}={len(x) if isinstance(x, (list, dict)) else x}" for k, x in v.items()
                 if isinstance(x, (list, dict, int, float)) and not isinstance(x, bool)]
        return ", ".join(parts[:12]) or f"키 {list(v)[:8]}"
    return repr(v)[:80]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", default=None)
    args = ap.parse_args()
    conn = get_db()
    weeks = conn.execute("SELECT week, created_at, length(payload) FROM weekly_briefings ORDER BY week DESC LIMIT 6").fetchall()
    print("최근 브리핑:", ", ".join(f"{w}({c}, {n}자)" for w, c, n in weeks))
    week = args.week or weeks[0][0]
    row = conn.execute("SELECT payload FROM weekly_briefings WHERE week = ?", (week,)).fetchone()
    if not row:
        print(f"{week} 브리핑 없음")
        return 1
    b = json.loads(row[0])
    print(f"\n== {week} (만든 시각 {b.get('generated_at')}) ==")
    for k, v in b.items():
        if k in ("week", "generated_at"):
            continue
        if k in ("us", "kr") and isinstance(v, dict):
            for kk, vv in v.items():
                print(f"  {k}.{kk}: {size(vv)}")
            continue
        print(f"  {k}: {size(v)}")
    # 이름만 몇 개 - 칸이 말이 되는지 눈으로
    for k in ("sentiment_heating", "catalysts"):
        items = b.get(k) or []
        print(f"\n  {k} 예: " + ", ".join(f"{x.get('market')}:{x.get('symbol')} {x.get('path') or ''}".strip() for x in items[:10]))
    wl = b.get("watchlist") or {}
    for side in ("added", "removed"):
        xs = wl.get(side) or []
        print(f"  watchlist.{side}: " + ", ".join(f"{x.get('market')}:{x.get('symbol')}" for x in xs[:10] if isinstance(x, dict)))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
