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

from datetime import date, timedelta

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
    """분기마다 쓸 값 하나씩. 연결재무 우선, 같은 구분이면 공시 원본(DART·SEC) 우선, 그다음 최근 수집분. 최신 분기부터."""
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


WITHDRAWN = "withdrawn"   # derived 값 - 출처가 더 이상 내놓지 않는 분기 표시(withdrawn_keys). 금액은 비어 있다.


def _is_withdrawn(rec: dict) -> bool:
    return rec.get("derived") == WITHDRAWN


def _quarter_end(year: int, quarter: int) -> date:
    return date(year, 12, 31) if quarter == 4 else date(year, quarter * 3 + 1, 1) - timedelta(days=1)


def _best_per_quarter(records, today: date | None = None) -> dict[tuple[int, int], dict]:
    """(연도, 분기)마다 _rank()가 제일 높은 레코드 하나만 남긴다.

    2026-11-05 두 가지를 뺀다:
      - 거둬들인 분기: 같은 출처·구분에서 가장 늦게 수집한 행이 derived='withdrawn'(withdrawn_keys로 덧붙인 표시)이면
        그 출처의 그 분기는 없는 것으로 본다. 다른 출처 행은 그대로 경쟁한다.
      - 아직 끝나지 않은 분기: 분기 말일이 오늘보다 뒤면 완결된 분기일 수 없다(분기 이름이 잘못 붙은 행).
    """
    today = today or date.today()
    recs = list(records)
    latest: dict[tuple, dict] = {}
    for rec in recs:
        k = (rec["fiscal_year"], rec["fiscal_quarter"], rec.get("source"), rec.get("fs_div"))
        cur = latest.get(k)
        if cur is None or str(rec.get("collected_at") or "") > str(cur.get("collected_at") or ""):
            latest[k] = rec
    best: dict[tuple[int, int], dict] = {}
    for rec in recs:
        key = (rec["fiscal_year"], rec["fiscal_quarter"])
        if _is_withdrawn(latest[(*key, rec.get("source"), rec.get("fs_div"))]) or _quarter_end(*key) > today:
            continue
        cur = best.get(key)
        if cur is None or _rank(rec) > _rank(cur):
            best[key] = rec
    return best


# 분기 이름 규칙(2026-11-05) - 분기 말일이 속한 달력 분기. 단, 다음 달력 분기의 첫 QUARTER_END_GRACE_DAYS일 안에 끝난 분기는
# 앞 분기로 본다. 52/53주 회계연도 회사는 분기 말일이 달력 분기 끝을 며칠 넘길 때가 있다(코카콜라 2026: 4/3·7/3·10/2).
# 예전 규칙은 이것을 다음 분기로 붙여, 같은 실제 분기가 두 이름으로(옛 열은 yfinance, 새 열은 SEC) 생기고 앞으로 올 분기 이름까지 차지했다.
QUARTER_END_GRACE_DAYS = 14


def calendar_quarter(end) -> tuple[int, int]:
    """분기 말일(date·datetime·pandas Timestamp) -> (연도, 분기)."""
    d = end - timedelta(days=QUARTER_END_GRACE_DAYS)
    return d.year, (d.month - 1) // 3 + 1


def withdrawn_keys(new_keys, prev: dict[tuple[int, int], tuple]) -> list[tuple[int, int]]:
    """이번 수집에서 받은 가장 늦은 분기보다 뒤인데 이번엔 없는 분기 - 전에 저장한 값이 아직 살아 있는 것만.

    수집기는 바뀐 분기만 새로 쌓으므로(이력 표), 분기 이름 규칙을 고쳐도 예전 이름으로 저장된 행은 그대로 남는다.
    그 분기에 derived='withdrawn'인 빈 행을 덧붙여(덮어쓰지 않음, 원칙 5) 읽는 쪽이 무시하게 한다. prev는 출처별 마지막 저장값
    (금액이 모두 빈 분기는 거둘 것이 없다고 보고 건너뛴다 - 이미 거둔 분기를 매주 다시 넣지 않게)."""
    new_keys = list(new_keys)
    if not new_keys:
        return []
    newest = max(new_keys)
    return sorted(k for k, v in prev.items() if k > newest and any(x is not None for x in v))


# 공시 원본(DART·SEC)을 yfinance보다 먼저 고른다(2026-10-17). 예전엔 구분이 같으면 늦게 수집한 쪽이라, 미국은
# 같은 분기에 SEC·yfinance 행이 둘 다 있으면 수집 순서에 따라 출처가 분기마다 섞였다(영업이익은 계정 차이로 소폭 다름).
# 공시 원본이 아직 없는 분기(막 발표돼 SEC 반영 전)는 yfinance를 그대로 쓴다.
SOURCE_PREFERENCE = ("DART", "SEC")


def _rank(rec: dict) -> tuple[int, int, str]:
    """고르기 우선순위. 연결재무가 먼저, 그다음 공시 원본 출처, 그다음 늦게 수집한 것(정정 반영)."""
    try:
        pref = len(FS_PREFERENCE) - FS_PREFERENCE.index(rec.get("fs_div") or "NA")
    except ValueError:
        pref = 0
    src = 1 if rec.get("source") in SOURCE_PREFERENCE else 0
    return (pref, src, str(rec.get("collected_at") or ""))


# 예전 이름을 쓰던 호출부를 위해 남겨둔다.
def get_quarters(conn, ticker: str, market: str) -> list[dict]:
    return select_quarters(conn, ticker, market)


def quarters_to_income_df(quarters: list[dict]):
    """select_quarters 결과(최신 분기부터) -> 재무 캐시 분기 손익과 같은 모양의 DataFrame(2026-11-05).

    행 'Total Revenue'·'Operating Income', 열 = 달력 분기 말일(최신이 앞). company_growth.quarterly_margin_change·
    quarterly_revenue_yoy가 캐시 DataFrame과 똑같이 읽게 하려는 것 - 분기가 비어 있어도 그대로 둔다(1년 전 분기는 날짜로 찾는다).
    분기 번호는 수집 때 분기 말일의 달력 분기로 정한 것이라(yfinance·SEC 같은 규칙) 말일도 달력 분기 끝으로 둔다."""
    import pandas as pd
    if not quarters:
        return None
    cols, rev, oi = [], [], []
    for r in quarters:
        cols.append(pd.Period(f"{int(r['fiscal_year'])}Q{int(r['fiscal_quarter'])}", freq="Q").end_time.normalize())
        rev.append(r.get("revenue"))
        oi.append(r.get("operating_income"))
    return pd.DataFrame([rev, oi], index=["Total Revenue", "Operating Income"], columns=cols, dtype="float")
