"""fetch_kr_investor_flows_pykrx.py가 만든 JSON을 kr_investor_flows 표에 저장한다 (2026-10-17).

kr_investor_flows(date, market, investor, value): market KOSPI/KOSDAQ, investor foreign/institution/individual,
value는 순매수 금액(원). 같은 날·시장·투자자는 최신 값으로 덮는다(장중·마감 직후 값이 확정값으로 바뀌는 것 - 지난 날짜의
확정값은 다시 와도 같은 값).

    python scripts/save_kr_investor_flows.py --in data/kr_investor_flows.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db.data_store import get_db

DDL = """
CREATE TABLE IF NOT EXISTS kr_investor_flows (
  date      TEXT NOT NULL,
  market    TEXT NOT NULL,
  investor  TEXT NOT NULL,
  value     REAL,
  PRIMARY KEY (date, market, investor)
)
"""


def save(conn, rows: list[dict]) -> int:
    conn.execute(DDL)
    vals = [(r["date"], r["market"], r["investor"], float(r["value"])) for r in rows if r.get("value") is not None]
    for i in range(0, len(vals), 100):
        chunk = vals[i:i + 100]
        conn.execute("INSERT OR REPLACE INTO kr_investor_flows (date, market, investor, value) VALUES "
                     + ", ".join(["(?, ?, ?, ?)"] * len(chunk)), tuple(v for r in chunk for v in r))
    conn.commit()
    return len(vals)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="path", default="data/kr_investor_flows.json")
    args = ap.parse_args()
    p = Path(args.path)
    if not p.exists():
        print(f"[kr-flows] {p} 없음 - 수집 단계가 실패했다. 저장 건너뜀", flush=True)
        return 0
    n = save(get_db(), json.loads(p.read_text(encoding="utf-8"))["rows"])
    print(f"[kr-flows] {n}행 저장", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
