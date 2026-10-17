"""관찰 노트 목록 (읽기 전용, 2026-10-17) - 저장 확인과 회고 진행 상황 점검용.

    python scripts/report_observations.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.db.data_store import get_db  # noqa: E402


def main() -> int:
    conn = get_db()
    obs = conn.execute("SELECT id, created_at, kind, market, theme_id, ticker, hypothesis, expects, week_start, snapshot "
                       "FROM observations ORDER BY id").fetchall()
    reviews = {}
    for oid, cp, at in conn.execute("SELECT observation_id, checkpoint, reviewed_at FROM observation_reviews").fetchall():
        reviews.setdefault(oid, []).append(f"{cp}주({str(at)[:10]})")
    print(f"관찰 노트 {len(obs)}개")
    for oid, created, kind, mkt, tid, tk, hyp, exp, wk, snap in obs:
        s = json.loads(snap or "{}")
        keys = ", ".join(f"{k}={s[k]}" for k in ("label", "news_arrow", "earn_arrow", "price_arrow") if k in s)
        print(f"\n#{oid} {created[:16]} {kind} {mkt} {tid or tk} (신호 주 {wk})")
        print(f"  가설: {hyp}")
        print(f"  기대: {exp}")
        print(f"  작성 시점 값: {keys or '(스냅샷 키: ' + ', '.join(list(s)[:8]) + ')'}")
        print(f"  회고: {', '.join(reviews.get(oid, [])) or '아직 없음'}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
