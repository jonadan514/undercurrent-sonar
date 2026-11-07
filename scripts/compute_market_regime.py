"""시장 환경(레짐) 주간 계산 - 2026-11-07, 레짐 모듈 2단계(사용자 결정: 상·하위 20% · 4주 · 평소 변화폭 1배 확정).

방금 끝난 주(기준 금요일)의 미국·한국 축 상태와 조합 이름을 market_regime_weekly에 쌓는다(덮어쓰지 않음). 일요일 정기 실행
(Compute Market Regime)이 브리핑 생성 전에 돈다. --weeks N이면 지난 N주를 한 번에 채운다(이미 있는 주는 건너뜀). GPT 없음.

    python scripts/compute_market_regime.py               # 방금 끝난 주
    python scripts/compute_market_regime.py --weeks 40    # 처음 채우기
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.analyzers import regime as rg
from src.db.data_store import get_db
from src.db.market_regime import ensure_schema, insert_weeks
from report_market_regime import fridays, load_series  # noqa: E402 - 같은 읽기를 쓴다

RULES = {"lookback": rg.LOOKBACK, "window": rg.WINDOW, "level_pct": rg.LEVEL_PCT, "z": rg.Z, "min_obs": rg.MIN_OBS}


def last_friday(today: date) -> date:
    """오늘 기준 이미 끝난 가장 최근 금요일(금요일 당일 실행이면 그 전 금요일 - 종가가 아직 안 들어왔을 수 있다)."""
    back = (today.weekday() - 4) % 7 or 7
    return today - timedelta(days=back)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=1)
    args = ap.parse_args()
    conn = get_db()
    ensure_schema(conn)
    series = load_series(conn)
    have = {(r[0], r[1]) for r in conn.execute("SELECT week, market FROM market_regime_weekly").fetchall()}
    now = datetime.utcnow().isoformat()
    rows = []
    for f in fridays(last_friday(date.today()), args.weeks):
        week = (date.fromisoformat(f) - timedelta(days=4)).isoformat()
        for market in ("US", "KR"):
            if (week, market) in have:
                continue
            st = rg.market_state(series, market, f)
            payload = {**rg.compact(st), "rules": RULES}
            rows.append((week, market, f, ",".join(c["id"] for c in st["combos"]), json.dumps(payload, ensure_ascii=False), now))
            axes = " · ".join(f"{a['name']}{rg.ARROW[a['dir']]}" for a in st["axes"].values())
            print(f"[regime] {week} {market} {axes} | " + (", ".join(c["name"] for c in st["combos"]) or "-"), flush=True)
    insert_weeks(conn, rows)
    print(f"[regime] 저장 {len(rows)}행 (이미 있던 주 건너뜀)", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
