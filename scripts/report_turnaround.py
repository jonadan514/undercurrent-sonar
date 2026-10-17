"""워치리스트 '실적 반전' 종목 표 (읽기 전용, 2026-10-17).

조건은 화면 버튼·브리핑과 같다(generate_weekly_briefing.is_turnaround): 매출 3년 정체·역성장인데 최근 1년(없으면 분기) 성장.
종목마다 업종·소속 테마(사업 소속만)·성장률·분기 이익률·밸류·F-Score를 한 줄로. 순위 없이 시장·지금 흐름 성장률 큰 순은
쓰지 않고 시장·업종·종목코드 순(원칙 1). 숫자는 DB 값 그대로.

    python scripts/report_turnaround.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from generate_weekly_briefing import is_turnaround  # noqa: E402
from src.db.data_store import get_db  # noqa: E402

THEMES_YAML = ROOT / "config" / "themes.yaml"
COLS = ("market", "symbol", "name", "sector", "growth_tier", "revenue_cagr_3y", "rev_ttm_tier", "rev_ttm_yoy",
        "rev_q_tier", "rev_q_yoy", "op_margin_q_now", "op_margin_q_change", "op_margin_q_status",
        "valuation_tier", "psr", "per", "piotroski", "market_cap")


def pct(v, digits=0):
    return "-" if v is None else f"{float(v) * 100:+.{digits}f}%"


def main() -> int:
    names = {}
    try:
        names = {t["id"]: t["name_ko"] for t in yaml.safe_load(open(THEMES_YAML, encoding="utf-8"))["themes"]}
    except Exception:  # noqa: BLE001
        pass
    conn = get_db()
    rows = [dict(zip(COLS, r)) for r in conn.execute(
        f"SELECT {', '.join(COLS)} FROM watchlist_candidates ORDER BY market, sector, symbol").fetchall()]
    themes: dict[tuple[str, str], list[str]] = {}
    for mkt in ("US", "KR"):
        for t, tid in conn.execute(
            """WITH latest AS (SELECT theme_id, MAX(run_id) AS run_id FROM theme_members
                               WHERE market = ? AND approved = 1 GROUP BY theme_id)
               SELECT tm.ticker, tm.theme_id FROM theme_members tm
               JOIN latest l ON l.theme_id = tm.theme_id AND l.run_id = tm.run_id
               WHERE tm.market = ? AND tm.approved = 1 AND tm.linkage IN ('direct', 'partial')""",
                (mkt, mkt)).fetchall():
            themes.setdefault((mkt, t), []).append(names.get(tid, tid))
    conn.close()

    picks = [r for r in rows if is_turnaround(r)]
    for mkt in ("US", "KR"):
        sel = [r for r in picks if r["market"] == mkt]
        print(f"\n## {mkt} 실적 반전 {len(sel)}종목 (시장·업종·종목코드 순)\n")
        print("| 종목 | 업종 | 테마 | 3년 | 지금(기준) | 분기 이익률 | 밸류 | PSR | PER | F |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for r in sel:
            ttm = r["rev_ttm_tier"] is not None
            now = f"{pct(r['rev_ttm_yoy'] if ttm else r['rev_q_yoy'])} ({'1년' if ttm else '분기'})"
            om = "-"
            if r["op_margin_q_now"] is not None:
                om = f"{float(r['op_margin_q_now']) * 100:.0f}%"
                if r["op_margin_q_change"] is not None:
                    om += f" ({float(r['op_margin_q_change']) * 100:+.0f}%p)"
            label = f"{r['name'] or r['symbol']}" if mkt == "KR" else f"{r['symbol']} {r['name'] or ''}"
            th = ", ".join(sorted(set(themes.get((mkt, r["symbol"]), [])))) or "-"
            psr = "-" if r["psr"] is None else f"{float(r['psr']):.1f}"
            per = "-" if r["per"] is None else f"{float(r['per']):.0f}"
            fs = "-" if r["piotroski"] is None else r["piotroski"]
            print(f"| {label} | {r['sector'] or '-'} | {th} | {r['growth_tier']} {pct(r['revenue_cagr_3y'], 1)} | {now} | "
                  f"{om} | {r['valuation_tier'] or '-'} | {psr} | {per} | {fs} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
