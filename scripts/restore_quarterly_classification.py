"""2026Q3 분기 분류 되살리기(2026-11-17, 사용자 결정 1).

11/17 3분기 재계산에서 뉴스 비율을 계산할 수 없어(수집원 변경 - 미국 9/28, 한국 11/16) 65개 테마가 전부 데이터부족이 됐고,
화면용 표(quarterly_theme_classification)가 같은 분기 키라 9/23에 계산해 둔 2026Q3 분류를 NULL로 덮었다.
두 실행의 로그(9/23 35860751625, 11/17 44024091384)에서 읽은 값(data/restore/quarterly_2026Q3_runs.json)으로:
  - 화면용 표: 9/23 행으로 되돌린다(9/23에 없던 테마는 11/17 행 그대로). 시장 참고값도 9/23 값으로.
  - 이력 표(quarterly_theme_classification_history): 9/23·11/17 두 실행을 각각 한 줄씩(이미 있으면 그대로).
로그에 없는 news_this_quarter만 비어 있다. 기본은 미리보기, --apply일 때만 쓴다.

    python scripts/restore_quarterly_classification.py            # 미리보기
    python scripts/restore_quarterly_classification.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db.data_store import get_db  # noqa: E402
from src.db.quarterly_classification import ensure_schema, upsert_market_reference  # noqa: E402

SRC = ROOT / "data" / "restore" / "quarterly_2026Q3_runs.json"
COLS = ["financial_on", "financial_changed", "financial_judged", "financial_ratio",
        "news_high", "news_ratio", "news_this_quarter", "classification"]


def _bit(v):
    return None if v is None else int(bool(v))


def row_values(r: dict, fy: int, fq: int, at: str) -> list:
    return [r["theme_id"], r["market"], fy, fq, _bit(r["financial_on"]), r["financial_changed"], r["financial_judged"],
            r["financial_ratio"], _bit(r["news_high"]), r["news_ratio"], r["news_this_quarter"], r["classification"], at]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    data = json.loads(SRC.read_text(encoding="utf-8"))
    old, new = data["2026-09-23"], data["2026-11-17"]
    fy, fq = old["fiscal_year"], old["fiscal_quarter"]
    cols = "theme_id, market, fiscal_year, fiscal_quarter, " + ", ".join(COLS) + ", computed_at"
    ph = ", ".join("?" for _ in range(len(COLS) + 5))

    conn = get_db()
    ensure_schema(conn)
    before = conn.execute("SELECT market, COUNT(*), SUM(CASE WHEN classification IS NOT NULL THEN 1 ELSE 0 END) "
                          "FROM quarterly_theme_classification WHERE fiscal_year = ? AND fiscal_quarter = ? GROUP BY market",
                          (fy, fq)).fetchall()
    print(f"지금 {fy}Q{fq} 화면용 표(시장, 행, 분류 있음): {[tuple(x) for x in before]}", flush=True)
    print(f"되살릴 9/23 행 {len(old['rows'])}개(분류 있음 {sum(1 for r in old['rows'] if r['classification'])}), "
          f"이력에 더할 11/17 행 {len(new['rows'])}개", flush=True)
    if not args.apply:
        print("미리보기 - --apply로 실제로 쓴다", flush=True)
        return 0

    for run in (old, new):   # 이력 - 두 실행 모두 한 줄씩
        for r in run["rows"]:
            conn.execute(f"INSERT OR IGNORE INTO quarterly_theme_classification_history ({cols}) VALUES ({ph})",
                         row_values(r, run["fiscal_year"], run["fiscal_quarter"], run["computed_at"]))
    for r in old["rows"]:    # 화면용 - 9/23 값으로 되돌림(조건 없이)
        conn.execute(f"INSERT INTO quarterly_theme_classification ({cols}) VALUES ({ph}) "
                     "ON CONFLICT(theme_id, market, fiscal_year, fiscal_quarter) DO UPDATE SET "
                     + ", ".join(f"{c} = excluded.{c}" for c in COLS + ["computed_at"]),
                     row_values(r, fy, fq, old["computed_at"]))
    for m in old["market_reference"]:
        upsert_market_reference(conn, m["market"], fy, fq, m["median_revenue_growth"], m["sample_size"], old["computed_at"])
    conn.commit()
    after = conn.execute("SELECT market, COUNT(*), SUM(CASE WHEN classification IS NOT NULL THEN 1 ELSE 0 END), MAX(computed_at) "
                         "FROM quarterly_theme_classification WHERE fiscal_year = ? AND fiscal_quarter = ? GROUP BY market",
                         (fy, fq)).fetchall()
    hist = conn.execute("SELECT computed_at, COUNT(*) FROM quarterly_theme_classification_history GROUP BY computed_at").fetchall()
    print(f"완료 - 화면용 표(시장, 행, 분류 있음, 계산 시각): {[tuple(x) for x in after]}", flush=True)
    print(f"이력 표(계산 시각, 행): {[tuple(x) for x in hist]}", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
