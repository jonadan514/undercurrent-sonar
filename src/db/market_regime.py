"""시장 환경 주간 이력(2026-11-07, 레짐 모듈 2단계) - scripts/compute_market_regime.py가 쓴다.

이력 표: (주, 시장)마다 한 번만 쓰고 덮어쓰지 않는다(원칙 5). 주 = 기준 금요일이 속한 주의 월요일(theme_signals와 같은 이름 -
일요일 정기 실행이 '방금 끝난 주'를 채운다). 기준값을 바꾸면 rules 지문이 달라지므로, 다시 계산할 때는 그 사실이 payload에 남는다.
"""
from __future__ import annotations

MARKET_REGIME_WEEKLY_DDL = """
CREATE TABLE IF NOT EXISTS market_regime_weekly (
  week         TEXT NOT NULL,   -- 그 주 월요일
  market       TEXT NOT NULL,   -- US / KR
  as_of        TEXT NOT NULL,   -- 기준 금요일
  combos       TEXT,            -- 조합 id 쉼표 구분(빠른 조회용), 없으면 빈 문자열
  payload      TEXT NOT NULL,   -- regime.compact() JSON + rules
  computed_at  TEXT NOT NULL,
  PRIMARY KEY (week, market)
)
"""


def ensure_schema(conn) -> None:
    conn.execute(MARKET_REGIME_WEEKLY_DDL)
    conn.commit()


def insert_weeks(conn, rows: list[tuple]) -> int:
    """rows: (week, market, as_of, combos, payload, computed_at). 이미 있는 주는 그대로 둔다."""
    for r in rows:
        conn.execute("INSERT OR IGNORE INTO market_regime_weekly (week, market, as_of, combos, payload, computed_at) "
                     "VALUES (?, ?, ?, ?, ?, ?)", r)
    conn.commit()
    return len(rows)
