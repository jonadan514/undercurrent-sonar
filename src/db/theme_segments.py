"""소속 기업의 가치사슬 구간(2026-11-05) - scripts/classify_value_chain.py가 쓴다.

이력 표다: 같은 (테마, 시장, 종목, 매핑 run, 구간 정의 지문)은 한 번만 쓰고 덮어쓰지 않는다(원칙 5). 매핑이 다시 승인되거나
themes.yaml 구간 글이 바뀌면 새 행이 생기고, 읽는 쪽은 최신 승인 run의 가장 늦게 분류한 행을 쓴다.
"""
from __future__ import annotations

THEME_MEMBER_SEGMENTS_DDL = """
CREATE TABLE IF NOT EXISTS theme_member_segments (
  theme_id       TEXT NOT NULL,
  market         TEXT NOT NULL,
  ticker         TEXT NOT NULL,
  run_id         TEXT NOT NULL,
  chain_hash     TEXT NOT NULL,
  segment        INTEGER NOT NULL,   -- themes.yaml value_chain의 (n), 0 = 어느 구간에도 안 맞음
  segment_label  TEXT,               -- 분류 당시 구간 첫 줄(구간 글이 바뀌어도 그때 무엇이었는지 남게)
  model          TEXT,
  classified_at  TEXT NOT NULL,
  PRIMARY KEY (theme_id, market, ticker, run_id, chain_hash)
)
"""


def ensure_schema(conn) -> None:
    conn.execute(THEME_MEMBER_SEGMENTS_DDL)
    conn.commit()


def classified_tickers(conn, theme_id: str, market: str, run_id: str, chain_hash: str) -> set[str]:
    rows = conn.execute("SELECT ticker FROM theme_member_segments WHERE theme_id = ? AND market = ? AND run_id = ? AND chain_hash = ?",
                        (theme_id, market, run_id, chain_hash)).fetchall()
    return {r[0] for r in rows}


def insert_segments(conn, rows: list[tuple]) -> None:
    """rows: (theme_id, market, ticker, run_id, chain_hash, segment, segment_label, model, classified_at)"""
    for r in rows:
        conn.execute("INSERT OR IGNORE INTO theme_member_segments (theme_id, market, ticker, run_id, chain_hash, segment, "
                     "segment_label, model, classified_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", r)
    conn.commit()
