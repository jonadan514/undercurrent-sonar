"""분기 재무 원본값 저장 (분기 재설계 docs/REDESIGN_SPEC.md 4-4).

**쌓고, 읽을 때 고른다.** 수집한 값은 지우거나 덮어쓰지 않고 그대로 쌓고(원칙 5),
어떤 값을 쓸지는 읽는 쪽에서 정한다.

왜 이렇게 바꿨나 (2026-09-21)
  전에는 (기업, 분기)를 기본키로 두고 충돌하면 COALESCE로 "비어 있던 칸만" 채웠다.
  그러면 처음에 별도재무(OFS)로 저장된 분기가 나중에 연결재무(CFS)를 확보해도 영원히
  별도재무로 남는다. "연결 우선, 없으면 별도"라는 SPEC 4-1 원칙과 정면으로 어긋나고,
  숫자가 틀린 줄 모르는 채로 분기 신호 계산 전체가 그 위에서 돌아간다.

고르는 규칙 (select_quarters)
  1. 같은 분기에 연결재무가 있으면 연결재무
  2. 없으면 별도재무
  3. 같은 구분 안에서는 가장 최근에 수집한 값 (정정공시 반영)
"""
from __future__ import annotations

QUARTERLY_FINANCIALS_RAW_DDL = """
CREATE TABLE IF NOT EXISTS quarterly_financials_raw (
  ticker           TEXT NOT NULL,
  market           TEXT NOT NULL,
  fiscal_year      INTEGER NOT NULL,
  fiscal_quarter   INTEGER NOT NULL,
  fs_div           TEXT NOT NULL,   -- 'CFS'(연결) | 'OFS'(별도) | 'NA'(yfinance 등 구분 없음)
  source           TEXT NOT NULL,   -- 'DART' | 'yfinance'
  collected_on     TEXT NOT NULL,   -- 수집일 'YYYY-MM-DD' (같은 날 재수집은 덮어쓴다)
  revenue          REAL,
  operating_income REAL,
  net_income       REAL,
  derived          TEXT,            -- 'reported' | 'annual_minus_9m' | 'bank_nii_plus_noninterest(_q4)'(SEC 은행)
  currency         TEXT,
  collected_at     TEXT NOT NULL,   -- 수집 시각(전체)
  PRIMARY KEY (ticker, market, fiscal_year, fiscal_quarter, fs_div, source, collected_on)
)
"""

# 예전 테이블. 새로 쓰지는 않지만 지우지 않는다(원칙 5) - 안에 있던 값은
# migrate_legacy_rows()가 raw로 옮긴다.
QUARTERLY_FINANCIALS_DDL = """
CREATE TABLE IF NOT EXISTS quarterly_financials (
  ticker           TEXT NOT NULL,
  market           TEXT NOT NULL,
  fiscal_year      INTEGER NOT NULL,
  fiscal_quarter   INTEGER NOT NULL,
  revenue          REAL,
  operating_income REAL,
  net_income       REAL,
  source           TEXT NOT NULL,
  fs_div           TEXT,
  derived          TEXT,
  currency         TEXT,
  collected_at     TEXT NOT NULL,
  PRIMARY KEY (ticker, market, fiscal_year, fiscal_quarter)
)
"""

FS_PREFERENCE = ("CFS", "OFS", "NA")   # 앞에 있을수록 먼저 고른다


def ensure_schema(conn) -> None:
    conn.execute(QUARTERLY_FINANCIALS_DDL)
    conn.execute(QUARTERLY_FINANCIALS_RAW_DDL)
    conn.commit()


def migrate_legacy_rows(conn) -> int:
    """예전 quarterly_financials의 값을 raw로 옮긴다. 여러 번 돌려도 안전하다.

    예전 테이블에는 수집일이 시각까지만 있어 앞 10자를 수집일로 쓴다. 같은 행이 이미
    raw에 있으면 기본키 충돌로 무시된다(INSERT OR IGNORE).

    옮긴 행 수는 전후의 COUNT(*) 차이로 센다. 운영 DB(_TursoConn)의 execute()는 커서가
    아니라 자기 자신을 돌려주고 rowcount가 없어서, rowcount에 기대면 몇 행을 옮겼든 0이 나온다.
    """
    before = _count_raw(conn)
    conn.execute(
        """
        INSERT OR IGNORE INTO quarterly_financials_raw
          (ticker, market, fiscal_year, fiscal_quarter, fs_div, source, collected_on,
           revenue, operating_income, net_income, derived, currency, collected_at)
        SELECT ticker, market, fiscal_year, fiscal_quarter,
               COALESCE(fs_div, 'NA'), source, substr(collected_at, 1, 10),
               revenue, operating_income, net_income, derived, currency, collected_at
        FROM quarterly_financials
        """
    )
    conn.commit()
    return _count_raw(conn) - before


def _count_raw(conn) -> int:
    """raw 테이블의 전체 행 수. Turso는 COUNT(*)도 문자열로 돌려주므로 int로 바꾼다."""
    return int(conn.execute("SELECT COUNT(*) FROM quarterly_financials_raw").fetchone()[0])


def insert_quarter(conn, ticker: str, market: str, year: int, quarter: int, values: dict,
                   source: str, currency: str, collected_at: str) -> None:
    """수집한 값을 그대로 쌓는다. 같은 날 같은 구분으로 다시 넣으면 그 행만 갱신된다."""
    fs_div = values.get("fs_div") or "NA"
    conn.execute(
        """
        INSERT INTO quarterly_financials_raw
          (ticker, market, fiscal_year, fiscal_quarter, fs_div, source, collected_on,
           revenue, operating_income, net_income, derived, currency, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, market, fiscal_year, fiscal_quarter, fs_div, source, collected_on)
        DO UPDATE SET
          revenue = excluded.revenue,
          operating_income = excluded.operating_income,
          net_income = excluded.net_income,
          derived = excluded.derived,
          currency = excluded.currency,
          collected_at = excluded.collected_at
        """,
        (ticker, market, year, quarter, fs_div, source, str(collected_at)[:10],
         values.get("revenue"), values.get("operating_income"), values.get("net_income"),
         values.get("derived"), currency, collected_at),
    )


_RAW_COLS = ("fiscal_year", "fiscal_quarter", "revenue", "operating_income", "net_income",
             "source", "fs_div", "derived", "collected_at")
_INT_COLS = ("fiscal_year", "fiscal_quarter")
_FLOAT_COLS = ("revenue", "operating_income", "net_income")


def _coerce(rec: dict) -> dict:
    """숫자 컬럼을 실제 숫자로 되돌린다.

    Turso HTTP 클라이언트는 INTEGER 컬럼을 **문자열**로 돌려준다(Hrana 프로토콜이 64비트
    정밀도 손실을 막으려고 정수를 문자열로 싣는데, _TursoConn.fetchall()이 타입 변환 없이
    그대로 넘긴다). 로컬 sqlite는 int를 주므로 테스트로는 드러나지 않는다 - 이 저장소는
    2026-09-01에 같은 함정으로 뉴스 기준선 계산이 `int + str`로 죽은 적이 있다.

    여기서 한 번 보정해두면 읽는 쪽이 `연도 - 1`, `분기 == 4` 같은 계산을 그냥 할 수 있다.
    """
    out = dict(rec)
    for key in _INT_COLS:
        if out.get(key) is not None:
            out[key] = int(out[key])
    for key in _FLOAT_COLS:
        if out.get(key) is not None:
            out[key] = float(out[key])
    return out


def select_quarters(conn, ticker: str, market: str) -> list[dict]:
    """분기마다 쓸 값 하나씩. 연결재무 우선, 같은 구분이면 최근 수집분. 최신 분기부터."""
    rows = conn.execute(
        f"SELECT {', '.join(_RAW_COLS)} FROM quarterly_financials_raw "
        "WHERE ticker = ? AND market = ?",
        (ticker, market),
    ).fetchall()
    best = _best_per_quarter(_coerce(dict(zip(_RAW_COLS, r))) for r in rows)
    return [best[k] for k in sorted(best, reverse=True)]


def select_quarters_bulk(conn, tickers: list[str], market: str) -> dict[str, list[dict]]:
    """select_quarters()를 여러 종목에 한 번의 쿼리로 (분기 4칸 분류 실행 스크립트가 쓴다).

    테마 소속 기업과 유니버스 전체(수백 종목)를 하나씩 select_quarters()로 조회하면
    운영 DB(Turso HTTP)에 종목 수만큼 왕복이 쌓인다 - SPEC §7의 "배치로" 원칙과 같은
    이유로 한 번의 IN 쿼리로 묶는다.

    반환에 없는 티커는 raw 표에 그 종목 행이 아예 없다는 뜻이다 - 호출부는
    `quarters_by_ticker.get(ticker, [])`로 select_quarters()가 빈 리스트를 돌려주는
    경우와 똑같이 다루면 된다.
    """
    if not tickers:
        return {}
    placeholders = ",".join("?" for _ in tickers)
    rows = conn.execute(
        f"SELECT ticker, {', '.join(_RAW_COLS)} FROM quarterly_financials_raw "
        f"WHERE market = ? AND ticker IN ({placeholders})",
        (market, *tickers),
    ).fetchall()

    raw_by_ticker: dict[str, list] = {}
    for r in rows:
        raw_by_ticker.setdefault(r[0], []).append(r[1:])

    out: dict[str, list[dict]] = {}
    for ticker, raw_rows in raw_by_ticker.items():
        best = _best_per_quarter(_coerce(dict(zip(_RAW_COLS, r))) for r in raw_rows)
        out[ticker] = [best[k] for k in sorted(best, reverse=True)]
    return out


def _best_per_quarter(records) -> dict[tuple[int, int], dict]:
    """(연도, 분기)마다 _rank()가 제일 높은 레코드 하나만 남긴다."""
    best: dict[tuple[int, int], dict] = {}
    for rec in records:
        key = (rec["fiscal_year"], rec["fiscal_quarter"])
        cur = best.get(key)
        if cur is None or _rank(rec) > _rank(cur):
            best[key] = rec
    return best


def _rank(rec: dict) -> tuple[int, str]:
    """고르기 우선순위. 연결재무가 먼저, 그다음 늦게 수집한 것."""
    try:
        pref = len(FS_PREFERENCE) - FS_PREFERENCE.index(rec.get("fs_div") or "NA")
    except ValueError:
        pref = 0
    return (pref, str(rec.get("collected_at") or ""))


# 예전 이름을 쓰던 호출부를 위해 남겨둔다.
def get_quarters(conn, ticker: str, market: str) -> list[dict]:
    return select_quarters(conn, ticker, market)
