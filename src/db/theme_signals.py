"""Phase A-3~6: 테마 신호(theme_news, theme_signals) 스키마 + 쓰기 함수.

SPEC: docs/radar/SPEC_phase_a_signals.md §1
"""
from __future__ import annotations

from datetime import date, timedelta


def signal_week_monday(today: date) -> date:
    """정기 파이프라인(뉴스·실적·주가·라벨)이 채울 주의 월요일 - **어제**가 속한 주.

    정기 실행은 일요일 22:00-23:00 UTC(SPEC §7)라 '오늘이 속한 주'와 같지만, GitHub 예약 실행은
    몇 시간씩 밀린다. 2026-09-28·10-05에는 월요일 00시(UTC)를 넘겨 시작해 막 시작된 새 주를 잡았고,
    미국 뉴스가 전 테마 0건(수집 실패 경고)으로, 한국은 몇 시간치 기사만 그 주에 저장됐다.
    하루를 빼면 월요일에 밀려 돌아도 방금 끝난 주를 채운다. 수요일 수동 실행 등 주 중간 실행은
    전과 같이 그 주를 잡는다."""
    d = today - timedelta(days=1)
    return d - timedelta(days=d.weekday())

THEME_NEWS_DDL = """
CREATE TABLE IF NOT EXISTS theme_news (
  theme_id     TEXT NOT NULL,
  market       TEXT NOT NULL,
  url_hash     TEXT NOT NULL,
  title        TEXT,
  url          TEXT,
  published_at TEXT,
  source       TEXT,
  week_start   TEXT NOT NULL,
  PRIMARY KEY (theme_id, market, url_hash)
)
"""

# SPEC 원안(§1.1)엔 news_backfilled 컬럼이 없지만, §2.4가 "backfilled=true 플래그를
# 남기고 첫 4주 판정은 참고용으로만 본다"고 명시적으로 요구해서 추가함 - SPEC 본문과
# 스키마 사이의 누락을 채운 것.
THEME_SIGNALS_DDL = """
CREATE TABLE IF NOT EXISTS theme_signals (
  theme_id          TEXT NOT NULL,
  market            TEXT NOT NULL,
  week_start        TEXT NOT NULL,

  news_count        INTEGER,
  news_baseline     REAL,
  news_ratio        REAL,
  news_arrow        TEXT,
  news_backfilled   INTEGER DEFAULT 0,

  earn_members      INTEGER,
  earn_improved     INTEGER,
  earn_insufficient INTEGER,
  earn_ratio        REAL,
  earn_arrow        TEXT,
  earn_as_of        TEXT,

  earn_surprise_n     INTEGER,
  earn_surprise_beat  INTEGER,
  earn_surprise_ratio REAL,
  earn_surprise_median REAL,

  price_median_ret  REAL,
  price_index_ret   REAL,
  price_excess      REAL,
  price_arrow       TEXT,
  price_volume_ratio REAL,

  label             TEXT,
  member_count      INTEGER,
  mapping_run_id    TEXT,
  computed_at       TEXT NOT NULL,

  PRIMARY KEY (theme_id, market, week_start)
)
"""


# 이미 만들어진 theme_signals에 뒤늦게 붙인 컬럼들. DDL만 고치면 기존 DB에는
# 반영되지 않아(CREATE TABLE IF NOT EXISTS라서) 쓰기 때 "no such column"이 난다.
LATE_COLUMNS = [("price_volume_ratio", "REAL"),
                ("earn_surprise_n", "INTEGER"),
                ("earn_surprise_beat", "INTEGER"),
                ("earn_surprise_ratio", "REAL"),
                ("earn_surprise_median", "REAL")]


# 분기 재설계(docs/REDESIGN_SPEC.md 6장)용 주간 기사 수 이력.
# theme_signals.news_count와 따로 두는 이유: (1) 기존 주간 파이프라인 행을 덮어쓰지 않는다
# (원칙 5), (2) 백필은 기사 원문을 저장하지 않고 집계만 남긴다 - 62주치 기사 원문은 100만 건이
# 넘어 저장 부담이 크고, 분기 비교에 필요한 것은 건수뿐이다.
# saturated_keywords > 0 이면 그 주 건수는 실제보다 작다(구글 100건 상한).
THEME_NEWS_WEEKLY_DDL = """
CREATE TABLE IF NOT EXISTS theme_news_weekly (
  theme_id           TEXT NOT NULL,
  market             TEXT NOT NULL,
  week_start         TEXT NOT NULL,
  article_count      INTEGER,
  raw_total          INTEGER,
  saturated_keywords INTEGER DEFAULT 0,
  expanded_keywords  INTEGER DEFAULT 0,
  failed_keywords    INTEGER DEFAULT 0,
  collected_at       TEXT,
  PRIMARY KEY (theme_id, market, week_start)
)
"""

EARNINGS_SURPRISE_DDL = """
CREATE TABLE IF NOT EXISTS earnings_surprise (
  ticker       TEXT PRIMARY KEY,
  market       TEXT,
  report_date  TEXT,
  surprise_pct REAL,
  eps_estimate REAL,
  eps_reported REAL,
  fetched_at   TEXT
)
"""


# 테마 소속 기업별 주간 값 (2026-10-05, 테마 흐름 이력 화면의 "이번 흐름을 만든 기업").
# theme_signals는 테마 중앙값만 남겨서 어느 기업이 흐름을 만들었는지 볼 수 없었다. 주가·실적 잡이
# 테마 중앙값을 낼 때 이미 계산하는 기업별 값을 같은 주 키로 같이 남긴다 - 새 조회 없음.
# 열은 축별로 나눠 쓴다(theme_signals와 같은 방식 - 주가 잡은 price_*, 실적 잡은 rev_*/earn_*만 갱신).
THEME_MEMBER_SIGNALS_DDL = """
CREATE TABLE IF NOT EXISTS theme_member_signals (
  theme_id     TEXT NOT NULL,
  market       TEXT NOT NULL,
  week_start   TEXT NOT NULL,
  ticker       TEXT NOT NULL,
  price_ret    REAL,     -- 20거래일 수익률 (theme_price_collector와 같은 창)
  rev_yoy      REAL,     -- 최근 분기 매출 전년동기 대비
  rev_quarter  TEXT,     -- rev_yoy의 분기 (예: 2026-Q2)
  earn_status  TEXT,     -- improved / not_improved / insufficient (시장 중앙값 기준)
  computed_at  TEXT,
  om_now       REAL,     -- 최근 분기 영업이익률 (company_growth.quarterly_margin_change)
  om_change    REAL,     -- 1년 전 같은 분기 대비 차이(소수, 0.02 = +2%p)
  om_status    TEXT,     -- 개선 / 악화 / 유지 / NULL(데이터부족)
  PRIMARY KEY (theme_id, market, week_start, ticker)
)
"""


def _upsert_member_rows(conn, cols: tuple[str, ...], rows: list[tuple], chunk_size: int = 100) -> None:
    """rows: (theme_id, market, week_start, ticker, *cols 값, computed_at). 한 INSERT에 여러 행을 묶는다
    (insert_theme_news_bulk와 같은 이유 - Turso HTTP 왕복 수)."""
    if not rows:
        return
    all_cols = ("theme_id", "market", "week_start", "ticker", *cols, "computed_at")
    one = "(" + ", ".join("?" * len(all_cols)) + ")"
    updates = ", ".join(f"{c} = excluded.{c}" for c in (*cols, "computed_at"))
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        params: list = []
        for r in chunk:
            params.extend(r)
        conn.execute(
            f"INSERT INTO theme_member_signals ({', '.join(all_cols)}) VALUES {', '.join([one] * len(chunk))} "
            f"ON CONFLICT(theme_id, market, week_start, ticker) DO UPDATE SET {updates}",
            tuple(params),
        )


def upsert_member_prices(conn, rows: list[tuple]) -> None:
    """rows: (theme_id, market, week_start, ticker, price_ret, computed_at)"""
    _upsert_member_rows(conn, ("price_ret",), rows)


def upsert_member_fcf(conn, rows: list[tuple]) -> None:
    """rows: (theme_id, market, week_start, ticker, fcf_yield_3y, fcf_negative_years, computed_at)"""
    _upsert_member_rows(conn, ("fcf_yield_3y", "fcf_negative_years"), rows)


def upsert_member_earnings(conn, rows: list[tuple]) -> None:
    """rows: (theme_id, market, week_start, ticker, rev_yoy, rev_quarter, earn_status,
              om_now, om_change, om_status, computed_at)"""
    _upsert_member_rows(conn, ("rev_yoy", "rev_quarter", "earn_status", "om_now", "om_change", "om_status"), rows)


# 처음 만든 뒤 추가된 기업별 열 - CREATE TABLE IF NOT EXISTS는 기존 표에 열을 더하지 않아 ALTER로 붙인다.
# fcf_*(2026-10-25): 테마 동료 비교(종목 상세)용. 3년 평균 FCF / 시가총액(company_cashflow.fcf_yield), 금융업은 계산 안 함.
MEMBER_LATE_COLUMNS = [("om_now", "REAL"), ("om_change", "REAL"), ("om_status", "TEXT"),
                       ("fcf_yield_3y", "REAL"), ("fcf_negative_years", "INTEGER")]


def ensure_schema(conn) -> None:
    conn.execute(THEME_NEWS_DDL)
    conn.execute(THEME_SIGNALS_DDL)
    conn.execute(EARNINGS_SURPRISE_DDL)
    conn.execute(THEME_NEWS_WEEKLY_DDL)
    conn.execute(THEME_MEMBER_SIGNALS_DDL)
    for name, coltype in MEMBER_LATE_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE theme_member_signals ADD COLUMN {name} {coltype}")
        except Exception:
            pass  # 이미 있음
    for name, coltype in LATE_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE theme_signals ADD COLUMN {name} {coltype}")
        except Exception:
            pass  # 이미 있는 컬럼 - 정상
    conn.commit()


def insert_theme_news(conn, theme_id: str, market: str, url_hash: str, title: str,
                       url: str, published_at: str, source: str, week_start: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO theme_news
          (theme_id, market, url_hash, title, url, published_at, source, week_start)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (theme_id, market, url_hash, title, url, published_at, source, week_start),
    )


def insert_theme_news_bulk(conn, theme_id: str, market: str, week_start: str,
                            articles: list[dict], chunk_size: int = 200) -> None:
    """articles를 chunk_size 단위로 묶어 한 번의 INSERT로 저장한다.

    기사마다 insert_theme_news()를 개별 호출하면 Turso HTTP 클라이언트는
    호출 하나마다 실제 HTTP 왕복을 하므로(Phase 0 §3에서 겪은 것과 같은
    문제), 뉴스가 많은 테마 하나의 한 주 분량(수백 건)만으로도 왕복이
    폭증한다. get_cached_financials_bulk()와 같은 처방 - 여러 값을 한
    INSERT 문의 VALUES에 묶는다."""
    if not articles:
        return
    for i in range(0, len(articles), chunk_size):
        _insert_news_chunk(conn, theme_id, market, week_start, articles[i:i + chunk_size])


NEWS_MIN_CHUNK = 25


def _insert_news_chunk(conn, theme_id: str, market: str, week_start: str, chunk: list[dict]) -> None:
    """한 묶음 저장. 실패하면(연결 계층 재시도까지 다 실패) 반으로 나눠 다시 - 큰 INSERT 하나 때문에
    그 테마·주 기사 전부를 잃지 않게(2026-10-05). INSERT OR IGNORE라 일부가 먼저 들어갔어도 다시 보내도 된다.
    NEWS_MIN_CHUNK보다 작아져도 실패하면 그대로 올린다(수집 실패로 드러나야 한다)."""
    placeholders = ", ".join(["(?, ?, ?, ?, ?, ?, ?, ?)"] * len(chunk))
    params: list = []
    for a in chunk:
        params.extend([
            theme_id, market, a["_url_hash"], a["title"], a["url"],
            a["published_at"], a["source"], week_start,
        ])
    try:
        conn.execute(
            "INSERT OR IGNORE INTO theme_news "
            "(theme_id, market, url_hash, title, url, published_at, source, week_start) "
            f"VALUES {placeholders}",
            tuple(params),
        )
    except Exception as e:
        if len(chunk) <= NEWS_MIN_CHUNK:
            raise
        half = len(chunk) // 2
        print(f"[theme_news] {theme_id}({market}) {len(chunk)}건 저장 실패({type(e).__name__}) - "
              f"{half}·{len(chunk) - half}건으로 나눠 다시", flush=True)
        _insert_news_chunk(conn, theme_id, market, week_start, chunk[:half])
        _insert_news_chunk(conn, theme_id, market, week_start, chunk[half:])


# 수집원이 바뀐 주(월요일). 이 주 이전 이력은 같은 시장이라도 규모가 달라 기준선에 잇지 않는다.
# KR: 구글 뉴스 RSS가 Actions IP에서 막혀(2026-09-28) 네이버 뉴스 API로 바꿨다. 같은 주제라도
# 네이버 건수가 구글보다 2-3배 많아서(AI 반도체 334 -> 721), 이어 붙이면 34개 테마 중 33개가
# 가짜 "급증"으로 나왔다(2026-10-01 실측). 네이버 이력이 BASELINE_MIN_WEEKS 쌓일 때까지 뉴스 축은
# na(데이터부족)로 남는다 - 탈락이 아니다.
# US: 같은 날 구글이 막혔고, 2026-10-04부터 Finnhub 기업 뉴스(소속 기업 뉴스 건수)로 바꿨다 - 정의 자체가
# 키워드 기사 수와 달라서 이전 이력과 잇지 않는다.
NEWS_SOURCE_SWITCH_WEEK = {"KR": "2026-09-28", "US": "2026-09-28"}


def news_history_since(theme: dict, market: str) -> str | None:
    """뉴스 기준선·분기 집계에 쓸 수 있는 가장 이른 주(월요일 ISO 날짜), 제한이 없으면 None.

    두 가지 중 더 늦은 것이다: (1) 테마 키워드가 바뀐 주(themes.yaml 유지보수 규칙 2),
    (2) 그 시장의 수집원이 바뀐 주(NEWS_SOURCE_SWITCH_WEEK)."""
    from datetime import date, timedelta
    candidates: list[str] = []
    kw_changed = theme.get("keywords_changed_at")
    if kw_changed:
        kc = kw_changed if isinstance(kw_changed, date) else date.fromisoformat(str(kw_changed))
        candidates.append((kc - timedelta(days=kc.weekday())).isoformat())
    if market in NEWS_SOURCE_SWITCH_WEEK:
        candidates.append(NEWS_SOURCE_SWITCH_WEEK[market])
    return max(candidates) if candidates else None


def get_prior_news_counts(conn, theme_id: str, market: str, week_start: str, weeks: int = 4,
                          since: str | None = None) -> list[int]:
    """week_start 이전 주들의 news_count를 최대 weeks개 가져온다 (baseline 계산용).
    news_count가 NULL인 행(계산 실패)은 제외한다.

    since(주 월요일 ISO 날짜)를 주면 그 주 이전 행은 쓰지 않는다 - 키워드가 바뀐 테마는
    바뀌기 전 건수와 추이를 잇지 않는다(themes.yaml 유지보수 규칙 2). 이 규칙은 문서에만
    있고 코드가 지키지 않았다(2026-09-15 건설기계 키워드 변경 때 확인).

    Turso HTTP 클라이언트(_TursoConn)는 정수 컬럼 값을 문자열로 반환한다
    (Hrana 프로토콜이 64비트 정밀도 손실 방지를 위해 정수를 문자열로 실어
    보내는데, _TursoConn.fetchall()이 타입 변환 없이 그대로 넘김) - 로컬
    sqlite3 폴백은 이미 int를 반환하므로 int()가 양쪽 다 안전하게 처리한다.
    """
    rows = conn.execute(
        """
        SELECT news_count FROM theme_signals
        WHERE theme_id = ? AND market = ? AND week_start < ? AND week_start >= ?
          AND news_count IS NOT NULL
        ORDER BY week_start DESC LIMIT ?
        """,
        (theme_id, market, week_start, since or "0000-00-00", weeks),
    ).fetchall()
    return [int(r[0]) for r in rows]


def upsert_news_signal(conn, theme_id: str, market: str, week_start: str,
                        news_count: int, news_baseline: float | None, news_ratio: float | None,
                        news_arrow: str, backfilled: bool, computed_at: str) -> None:
    """theme_signals에 뉴스 축만 채워 넣는다. 실적/주가 축(Phase A-4/A-5)이
    나중에 같은 행을 UPDATE하므로 여기서는 뉴스 관련 컬럼만 갱신하고 나머지는
    건드리지 않는다."""
    conn.execute(
        """
        INSERT INTO theme_signals
          (theme_id, market, week_start, news_count, news_baseline, news_ratio,
           news_arrow, news_backfilled, computed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(theme_id, market, week_start) DO UPDATE SET
          news_count = excluded.news_count,
          news_baseline = excluded.news_baseline,
          news_ratio = excluded.news_ratio,
          news_arrow = excluded.news_arrow,
          news_backfilled = excluded.news_backfilled,
          computed_at = excluded.computed_at
        """,
        (theme_id, market, week_start, news_count, news_baseline, news_ratio,
         news_arrow, 1 if backfilled else 0, computed_at),
    )


def upsert_earn_signal(conn, theme_id: str, market: str, week_start: str,
                        earn_members: int, earn_improved: int, earn_insufficient: int,
                        earn_ratio: float | None, earn_arrow: str, earn_as_of: str | None,
                        member_count: int, mapping_run_id: str, computed_at: str,
                        surprise: dict | None = None) -> None:
    """theme_signals에 실적 축만 채워 넣는다(뉴스/주가 축은 건드리지 않음).

    실적 축은 주간 신호가 아니라 분기에 한 번만 바뀐다(SPEC §3.4) - 그래도
    매주 도는 파이프라인이 같은 값을 반복해서 그 주 행에 채워 넣는다. 그래야
    화면이 "이번 주 상태"를 보여줄 때 세 축이 다 채워진 최신 행 하나만 보면
    되고, earn_as_of로 "이 값은 지난 분기 것"임을 표시할 수 있다."""
    conn.execute(
        """
        INSERT INTO theme_signals
          (theme_id, market, week_start, earn_members, earn_improved, earn_insufficient,
           earn_ratio, earn_arrow, earn_as_of, earn_surprise_n, earn_surprise_beat,
           earn_surprise_ratio, earn_surprise_median, member_count, mapping_run_id, computed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(theme_id, market, week_start) DO UPDATE SET
          earn_members = excluded.earn_members,
          earn_improved = excluded.earn_improved,
          earn_insufficient = excluded.earn_insufficient,
          earn_ratio = excluded.earn_ratio,
          earn_arrow = excluded.earn_arrow,
          earn_as_of = excluded.earn_as_of,
          earn_surprise_n = excluded.earn_surprise_n,
          earn_surprise_beat = excluded.earn_surprise_beat,
          earn_surprise_ratio = excluded.earn_surprise_ratio,
          earn_surprise_median = excluded.earn_surprise_median,
          member_count = excluded.member_count,
          mapping_run_id = excluded.mapping_run_id,
          computed_at = excluded.computed_at
        """,
        (theme_id, market, week_start, earn_members, earn_improved, earn_insufficient,
         earn_ratio, earn_arrow, earn_as_of,
         (surprise or {}).get("n"), (surprise or {}).get("beat"),
         (surprise or {}).get("ratio"), (surprise or {}).get("median_pct"),
         member_count, mapping_run_id, computed_at),
    )


def upsert_price_signal(conn, theme_id: str, market: str, week_start: str,
                         price_median_ret: float | None, price_index_ret: float | None,
                         price_excess: float | None, price_arrow: str,
                         member_count: int, mapping_run_id: str, computed_at: str,
                         price_volume_ratio: float | None = None) -> None:
    """theme_signals에 주가 축만 채워 넣는다(뉴스/실적 축은 건드리지 않음)."""
    conn.execute(
        """
        INSERT INTO theme_signals
          (theme_id, market, week_start, price_median_ret, price_index_ret, price_excess,
           price_arrow, price_volume_ratio, member_count, mapping_run_id, computed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(theme_id, market, week_start) DO UPDATE SET
          price_median_ret = excluded.price_median_ret,
          price_index_ret = excluded.price_index_ret,
          price_excess = excluded.price_excess,
          price_arrow = excluded.price_arrow,
          price_volume_ratio = excluded.price_volume_ratio,
          member_count = excluded.member_count,
          mapping_run_id = excluded.mapping_run_id,
          computed_at = excluded.computed_at
        """,
        (theme_id, market, week_start, price_median_ret, price_index_ret, price_excess,
         price_arrow, price_volume_ratio, member_count, mapping_run_id, computed_at),
    )


def get_week_signals(conn, market: str, week_start: str) -> list[dict]:
    """해당 주의 theme_signals 전체 행을 라벨 계산에 필요한 컬럼만 가져온다."""
    rows = conn.execute(
        """
        SELECT theme_id, news_arrow, earn_arrow, price_arrow
        FROM theme_signals WHERE market = ? AND week_start = ?
        """,
        (market, week_start),
    ).fetchall()
    return [{"theme_id": r[0], "news_arrow": r[1], "earn_arrow": r[2], "price_arrow": r[3]} for r in rows]


def update_theme_label(conn, theme_id: str, market: str, week_start: str, label: str | None) -> None:
    """이미 존재하는 행(뉴스/실적/주가 축 upsert로 먼저 생성됨)의 label만 갱신한다.
    라벨은 세 축이 다 있어야 계산되므로 새 행을 만들 일이 없다 - UPDATE만."""
    conn.execute(
        "UPDATE theme_signals SET label = ? WHERE theme_id = ? AND market = ? AND week_start = ?",
        (label, theme_id, market, week_start),
    )


def get_approved_theme_members(conn, theme_id: str, market: str,
                                linkages: tuple[str, ...] = ("direct", "partial")) -> list[dict]:
    """SPEC §5 - "현재 유효 매핑은 최신 run_id + approved=1로 조회한다"를 그대로
    구현. approved=1이라고 전부 모으면, 나중에 분기 재매핑이 또 승인됐을 때
    예전 run의 승인 행과 중복 집계된다 - 가장 최근 run_id 하나로 고정한다.
    linkage 필터는 SPEC §3.2 기본값(peripheral 제외)."""
    latest_run = conn.execute(
        "SELECT MAX(run_id) FROM theme_members WHERE theme_id = ? AND market = ? AND approved = 1",
        (theme_id, market),
    ).fetchone()
    if not latest_run or not latest_run[0]:
        return []
    run_id = latest_run[0]

    placeholders = ",".join("?" for _ in linkages)
    rows = conn.execute(
        f"""
        SELECT ticker FROM theme_members
        WHERE theme_id = ? AND market = ? AND run_id = ? AND approved = 1 AND linkage IN ({placeholders})
        """,
        (theme_id, market, run_id, *linkages),
    ).fetchall()
    return [{"ticker": r[0], "run_id": run_id} for r in rows]


def get_surprises(conn, tickers: list[str]) -> dict[str, dict]:
    """종목별 최근 서프라이즈. 빈 목록이면 빈 dict."""
    if not tickers:
        return {}
    out: dict[str, dict] = {}
    chunk_size = 200  # SQL 변수 한도 회피
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        rows = conn.execute(
            "SELECT ticker, market, report_date, surprise_pct, eps_estimate, eps_reported, fetched_at "
            f"FROM earnings_surprise WHERE ticker IN ({','.join('?' * len(chunk))})",
            tuple(chunk),
        ).fetchall()
        for r in rows:
            out[r[0]] = {"market": r[1], "report_date": r[2],
                         "surprise_pct": float(r[3]) if r[3] is not None else None,
                         "eps_estimate": r[4], "eps_reported": r[5], "fetched_at": r[6]}
    return out


def upsert_surprise(conn, ticker: str, market: str, report_date: str | None,
                    surprise_pct: float | None, eps_estimate: float | None,
                    eps_reported: float | None, fetched_at: str) -> None:
    conn.execute(
        """
        INSERT INTO earnings_surprise
          (ticker, market, report_date, surprise_pct, eps_estimate, eps_reported, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
          market = excluded.market,
          report_date = excluded.report_date,
          surprise_pct = excluded.surprise_pct,
          eps_estimate = excluded.eps_estimate,
          eps_reported = excluded.eps_reported,
          fetched_at = excluded.fetched_at
        """,
        (ticker, market, report_date, surprise_pct, eps_estimate, eps_reported, fetched_at),
    )


def upsert_news_weekly(conn, theme_id: str, market: str, week_start: str, article_count: int,
                       raw_total: int, saturated: int, expanded: int, failed: int,
                       collected_at: str) -> None:
    """주간 기사 수 이력(분기 집계용). 같은 주를 다시 수집하면 최신 값으로 갱신한다."""
    conn.execute(
        """
        INSERT INTO theme_news_weekly
          (theme_id, market, week_start, article_count, raw_total,
           saturated_keywords, expanded_keywords, failed_keywords, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(theme_id, market, week_start) DO UPDATE SET
          article_count = excluded.article_count,
          raw_total = excluded.raw_total,
          saturated_keywords = excluded.saturated_keywords,
          expanded_keywords = excluded.expanded_keywords,
          failed_keywords = excluded.failed_keywords,
          collected_at = excluded.collected_at
        """,
        (theme_id, market, week_start, article_count, raw_total,
         saturated, expanded, failed, collected_at),
    )


def get_collected_news_weeks(conn, market: str) -> set[tuple[str, str]]:
    """이미 수집한 (theme_id, week_start) 집합 - 백필 재실행 때 건너뛰기용."""
    rows = conn.execute(
        "SELECT theme_id, week_start FROM theme_news_weekly WHERE market = ?", (market,)
    ).fetchall()
    return {(r[0], r[1]) for r in rows}


def get_weekly_news_counts(conn, theme_id: str, market: str,
                           since: str | None = None) -> dict[str, int]:
    """주간 기사 수를 두 표에서 합쳐 읽는다 (분기 집계용, REDESIGN_SPEC 6-3).

    같은 주간 건수가 두 곳에 나뉘어 있다.
      - theme_news_weekly: 과거를 채운 백필 결과
      - theme_signals.news_count: 매주 도는 수집이 남기는 값
    둘 다 collect_theme_news()로 같은 주를 조회해 중복 제거 후 센 값이라 이어 붙일 수 있다.
    같은 주가 양쪽에 있으면 백필 표를 쓴다(포화 키워드 정보가 함께 있는 쪽).

    since(주 월요일)를 주면 그 주 이전은 빼고 읽는다 - 키워드가 바뀐 테마는 바뀌기 전
    건수와 잇지 않는다(themes.yaml 유지보수 규칙 2).

    Turso HTTP 클라이언트는 정수 컬럼을 문자열로 돌려주므로 int()로 맞춘다.
    """
    floor = since or "0000-00-00"
    out: dict[str, int] = {}
    rows = conn.execute(
        "SELECT week_start, news_count FROM theme_signals "
        "WHERE theme_id = ? AND market = ? AND week_start >= ? AND news_count IS NOT NULL",
        (theme_id, market, floor),
    ).fetchall()
    for week_start, count in rows:
        out[week_start] = int(count)

    rows = conn.execute(
        "SELECT week_start, article_count FROM theme_news_weekly "
        "WHERE theme_id = ? AND market = ? AND week_start >= ? AND article_count IS NOT NULL",
        (theme_id, market, floor),
    ).fetchall()
    for week_start, count in rows:
        out[week_start] = int(count)      # 백필 표가 이긴다
    return out
