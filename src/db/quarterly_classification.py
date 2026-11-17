"""테마 4칸 분류 이력 저장 (분기 재설계 docs/REDESIGN_SPEC.md 7장).

원칙 5(이력 테이블은 덮어쓰지 않는다)는 **다른 분기**의 값을 지우지 않는다는 뜻이다.
같은 분기를 다시 계산해 갱신하는 것은 허용한다 - `theme_signals`의 주간 upsert와 같은
패턴이다. DART 정정공시나 뉴스 재수집으로 숫자가 바뀌면 그 분기 행을 최신값으로
갱신해야 다음 조회가 틀린 채로 남지 않는다. 다른 분기 행은 건드리지 않으므로 "지난
분기 대비 바뀐 테마"를 그대로 비교할 수 있다(7-3 마지막 줄).

2026-11-17 보완: 같은 분기를 다시 계산했는데 뉴스 비율을 계산할 수 없어(수집원 변경) 결과가 전부 데이터부족이 되자,
9/23에 계산해 둔 2026Q3 분류가 NULL로 덮였다. 그래서 (1) 계산할 때마다 `quarterly_theme_classification_history`에
한 줄씩 쌓고(덮어쓰지 않음), (2) 화면이 읽는 이 표는 새 결과에 분류가 있을 때만(또는 원래 분류가 없을 때만) 갱신한다 -
분류가 있는 행을 데이터부족으로 덮지 않는다. 최신 재무 숫자는 이력 표에서 따로 읽는다(/api/quarterly).

재무·뉴스 판정은 True/False/데이터부족(None) 3값이지만 sqlite에는 bool 타입이 없다.
1/0/NULL로 저장하고 읽을 때 bool로 되돌린다(`_coerce`) - INTEGER 0과 "판정 안 됨"을
구분하려면 NULL이 꼭 필요하다.
"""
from __future__ import annotations

QUARTERLY_THEME_CLASSIFICATION_DDL = """
CREATE TABLE IF NOT EXISTS quarterly_theme_classification (
  theme_id           TEXT NOT NULL,
  market             TEXT NOT NULL,
  fiscal_year        INTEGER NOT NULL,
  fiscal_quarter     INTEGER NOT NULL,
  financial_on       INTEGER,   -- 1/0/NULL(데이터부족) - 재무 신호 "켜짐" (7-1)
  financial_changed  INTEGER,   -- 변화 기업 수
  financial_judged   INTEGER,   -- 판정 가능(데이터부족 아닌) 기업 수
  financial_ratio    REAL,
  news_high          INTEGER,   -- 1/0/NULL(데이터부족) - 뉴스 "많음" (7-2)
  news_ratio         REAL,
  news_this_quarter  INTEGER,
  classification     TEXT,      -- 4칸 이름, 데이터부족이면 NULL (7-3)
  computed_at        TEXT NOT NULL,
  PRIMARY KEY (theme_id, market, fiscal_year, fiscal_quarter)
)
"""


QUARTERLY_MARKET_REFERENCE_DDL = """
CREATE TABLE IF NOT EXISTS quarterly_market_reference (
  market                 TEXT NOT NULL,
  fiscal_year            INTEGER NOT NULL,
  fiscal_quarter         INTEGER NOT NULL,
  median_revenue_growth  REAL,      -- NULL이면 유니버스를 못 읽는 등으로 계산 불가
  sample_size            INTEGER NOT NULL,
  computed_at            TEXT NOT NULL,
  PRIMARY KEY (market, fiscal_year, fiscal_quarter)
)
"""
# 시장 유니버스 전체의 매출 증가율 중앙값 (5-1 화면 참고값 - 판정에는 쓰지 않는다).
# 매 화면 요청마다 유니버스 수백 종목을 다시 계산하지 않도록 분기 실행 때 한 번 저장해둔다.


# 계산할 때마다 한 줄(2026-11-17) - 같은 분기를 다시 계산해도 예전 줄은 그대로(원칙 5)
QUARTERLY_THEME_CLASSIFICATION_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS quarterly_theme_classification_history (
  theme_id           TEXT NOT NULL,
  market             TEXT NOT NULL,
  fiscal_year        INTEGER NOT NULL,
  fiscal_quarter     INTEGER NOT NULL,
  financial_on       INTEGER,
  financial_changed  INTEGER,
  financial_judged   INTEGER,
  financial_ratio    REAL,
  news_high          INTEGER,
  news_ratio         REAL,
  news_this_quarter  INTEGER,
  classification     TEXT,
  computed_at        TEXT NOT NULL,
  PRIMARY KEY (theme_id, market, fiscal_year, fiscal_quarter, computed_at)
)
"""


def ensure_schema(conn) -> None:
    conn.execute(QUARTERLY_THEME_CLASSIFICATION_DDL)
    conn.execute(QUARTERLY_THEME_CLASSIFICATION_HISTORY_DDL)
    conn.execute(QUARTERLY_MARKET_REFERENCE_DDL)
    conn.commit()


def upsert_market_reference(conn, market: str, year: int, quarter: int,
                            median_growth: float | None, sample_size: int,
                            computed_at: str) -> None:
    """이 분기 이 시장의 참고값을 기록한다. 같은 분기를 다시 계산하면 이 행만 갱신된다."""
    conn.execute(
        """
        INSERT INTO quarterly_market_reference
          (market, fiscal_year, fiscal_quarter, median_revenue_growth, sample_size, computed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(market, fiscal_year, fiscal_quarter) DO UPDATE SET
          median_revenue_growth = excluded.median_revenue_growth,
          sample_size = excluded.sample_size,
          computed_at = excluded.computed_at
        """,
        (market, year, quarter, median_growth, sample_size, computed_at),
    )
    conn.commit()


def get_market_reference(conn, market: str, year: int, quarter: int) -> dict | None:
    row = conn.execute(
        "SELECT median_revenue_growth, sample_size, computed_at FROM quarterly_market_reference "
        "WHERE market = ? AND fiscal_year = ? AND fiscal_quarter = ?",
        (market, year, quarter),
    ).fetchone()
    if row is None:
        return None
    median, sample, at = row
    return {"median_revenue_growth": float(median) if median is not None else None,
            "sample_size": int(sample), "computed_at": at}


def _bit(value: bool | None) -> int | None:
    """bool|None -> 1/0/None. sqlite에는 bool이 없어 정수로 저장한다."""
    return None if value is None else int(bool(value))


def upsert_classification(conn, theme_id: str, market: str, year: int, quarter: int, *,
                          financial: dict, news: dict, classification: str | None,
                          computed_at: str) -> None:
    """이 분기 이 테마의 분류를 기록한다. 이력 표에는 늘 한 줄 더하고, 화면용 표는 같은 분기 행을 갱신하되
    분류가 있던 행을 데이터부족(분류 NULL)으로 덮지는 않는다(2026-11-17, 모듈 설명 참고).

    financial은 `theme_quarterly_classification.financial_signal()`의 반환값,
    news는 {"high": bool|None, "ratio": float|None, "this_quarter": int|None} 형태
    (news_ratio()의 반환값에 quarterly_thresholds.is_news_high() 결과를 합친 것)다.
    """
    values = (theme_id, market, year, quarter,
              _bit(financial.get("on")), financial.get("changed"), financial.get("judged"),
              financial.get("ratio"),
              _bit(news.get("high")), news.get("ratio"), news.get("this_quarter"),
              classification, computed_at)
    conn.execute(
        """
        INSERT OR IGNORE INTO quarterly_theme_classification_history
          (theme_id, market, fiscal_year, fiscal_quarter,
           financial_on, financial_changed, financial_judged, financial_ratio,
           news_high, news_ratio, news_this_quarter, classification, computed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, values)
    conn.execute(
        """
        INSERT INTO quarterly_theme_classification
          (theme_id, market, fiscal_year, fiscal_quarter,
           financial_on, financial_changed, financial_judged, financial_ratio,
           news_high, news_ratio, news_this_quarter, classification, computed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(theme_id, market, fiscal_year, fiscal_quarter) DO UPDATE SET
          financial_on = excluded.financial_on,
          financial_changed = excluded.financial_changed,
          financial_judged = excluded.financial_judged,
          financial_ratio = excluded.financial_ratio,
          news_high = excluded.news_high,
          news_ratio = excluded.news_ratio,
          news_this_quarter = excluded.news_this_quarter,
          classification = excluded.classification,
          computed_at = excluded.computed_at
        WHERE excluded.classification IS NOT NULL OR quarterly_theme_classification.classification IS NULL
        """, values)
    conn.commit()


_ROW_COLS = ("fiscal_year", "fiscal_quarter", "financial_on", "financial_changed",
             "financial_judged", "financial_ratio", "news_high", "news_ratio",
             "news_this_quarter", "classification", "computed_at")
_INT_COLS = ("fiscal_year", "fiscal_quarter", "financial_changed", "financial_judged",
             "news_this_quarter")
_FLOAT_COLS = ("financial_ratio", "news_ratio")
_BOOL_COLS = ("financial_on", "news_high")


def _coerce(rec: dict) -> dict:
    """Turso HTTP는 INTEGER를 문자열로 돌려준다 - 읽을 때 한 번 실제 타입으로 되돌린다.

    2026-09-01 뉴스 기준선, 2026-09-21 분기 재무 조회가 같은 함정으로 틀렸던 적이 있다.
    """
    out = dict(rec)
    for key in _INT_COLS:
        if out.get(key) is not None:
            out[key] = int(out[key])
    for key in _FLOAT_COLS:
        if out.get(key) is not None:
            out[key] = float(out[key])
    for key in _BOOL_COLS:
        if out.get(key) is not None:
            out[key] = bool(int(out[key]))
    return out


def get_classification(conn, theme_id: str, market: str, year: int, quarter: int) -> dict | None:
    """이 테마의 특정 분기 분류. 계산한 적 없으면 None(빈 화면 - 데이터부족과 다르다)."""
    row = conn.execute(
        f"SELECT {', '.join(_ROW_COLS)} FROM quarterly_theme_classification "
        "WHERE theme_id = ? AND market = ? AND fiscal_year = ? AND fiscal_quarter = ?",
        (theme_id, market, year, quarter),
    ).fetchone()
    if row is None:
        return None
    return _coerce(dict(zip(_ROW_COLS, row)))


def get_theme_history(conn, theme_id: str, market: str) -> list[dict]:
    """그 테마의 분기별 분류 이력, 최신 분기부터."""
    rows = conn.execute(
        f"SELECT {', '.join(_ROW_COLS)} FROM quarterly_theme_classification "
        "WHERE theme_id = ? AND market = ? ORDER BY fiscal_year DESC, fiscal_quarter DESC",
        (theme_id, market),
    ).fetchall()
    return [_coerce(dict(zip(_ROW_COLS, r))) for r in rows]


def previous_classification(conn, theme_id: str, market: str, year: int, quarter: int) -> dict | None:
    """직전 분기의 분류 (7-3 마지막 줄: 지난 분기 대비 바뀐 테마 보기)."""
    py, pq = (year, quarter - 1) if quarter > 1 else (year - 1, 4)
    return get_classification(conn, theme_id, market, py, pq)
