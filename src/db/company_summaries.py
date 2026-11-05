"""기업 카드 사업 요약 한국어판(2026-11-05) - scripts/gen_company_summaries_ko.py가 쓴다.

이력 표: (시장, 종목, 원문 지문)마다 한 번만 쓰고 덮어쓰지 않는다(원칙 5). 영문 원문이 바뀌면 새 지문으로 새 행이 생기고,
화면(/api/company)은 가장 늦게 만든 행을 쓴다.
"""
from __future__ import annotations

COMPANY_SUMMARIES_KO_DDL = """
CREATE TABLE IF NOT EXISTS company_summaries_ko (
  market      TEXT NOT NULL,
  symbol      TEXT NOT NULL,
  src_hash    TEXT NOT NULL,   -- 옮긴 영문 원문(companyProfiles.json d)의 지문
  summary_ko  TEXT NOT NULL,
  model       TEXT,
  created_at  TEXT NOT NULL,
  PRIMARY KEY (market, symbol, src_hash)
)
"""


def ensure_schema(conn) -> None:
    conn.execute(COMPANY_SUMMARIES_KO_DDL)
    conn.commit()


def existing_keys(conn) -> set[tuple[str, str, str]]:
    return {(r[0], r[1], r[2]) for r in conn.execute("SELECT market, symbol, src_hash FROM company_summaries_ko").fetchall()}


def insert_summaries(conn, rows: list[tuple]) -> None:
    """rows: (market, symbol, src_hash, summary_ko, model, created_at)"""
    for r in rows:
        conn.execute("INSERT OR IGNORE INTO company_summaries_ko (market, symbol, src_hash, summary_ko, model, created_at) "
                     "VALUES (?, ?, ?, ?, ?, ?)", r)
    conn.commit()
