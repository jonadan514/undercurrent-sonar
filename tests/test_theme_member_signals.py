"""theme_member_signals - 주가·실적 잡이 같은 행의 서로 다른 열을 채우고, 다시 돌면 덮어쓴다."""
import sqlite3

from src.db.theme_signals import ensure_schema, upsert_member_earnings, upsert_member_prices


def test_price_and_earnings_merge_into_one_row():
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    upsert_member_prices(conn, [("ai", "US", "2026-09-28", "NVDA", 0.12, "t1"),
                                ("ai", "US", "2026-09-28", "AMD", None, "t1")])
    upsert_member_earnings(conn, [("ai", "US", "2026-09-28", "NVDA", 0.55, "2026-Q2", "improved",
                                   0.62, 0.03, "개선", "t2")])
    rows = dict((r[0], r[1:]) for r in conn.execute(
        "SELECT ticker, price_ret, rev_yoy, rev_quarter, earn_status, om_now, om_change, om_status FROM theme_member_signals"))
    assert rows["NVDA"] == (0.12, 0.55, "2026-Q2", "improved", 0.62, 0.03, "개선")
    assert rows["AMD"] == (None,) * 7      # 수익률 없음 = 데이터부족, 행은 남는다


def test_rerun_same_week_updates_not_duplicates():
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    upsert_member_prices(conn, [("ai", "US", "2026-09-28", "NVDA", 0.12, "t1")])
    upsert_member_prices(conn, [("ai", "US", "2026-09-28", "NVDA", 0.20, "t2")])
    assert conn.execute("SELECT COUNT(*), MAX(price_ret) FROM theme_member_signals").fetchone() == (1, 0.20)


def test_many_rows_are_chunked():
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    upsert_member_prices(conn, [("ai", "KR", "2026-09-28", f"{i:06d}", i / 1000, "t") for i in range(400)])
    assert conn.execute("SELECT COUNT(*) FROM theme_member_signals").fetchone()[0] == 400


def test_late_columns_added_to_existing_table():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE theme_member_signals (theme_id TEXT, market TEXT, week_start TEXT, ticker TEXT, "
                 "price_ret REAL, rev_yoy REAL, rev_quarter TEXT, earn_status TEXT, computed_at TEXT, "
                 "PRIMARY KEY (theme_id, market, week_start, ticker))")      # 처음 버전 표
    ensure_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(theme_member_signals)")}
    assert {"om_now", "om_change", "om_status"} <= cols


def test_fcf_columns_merge_into_member_row():
    from src.db.theme_signals import upsert_member_fcf
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    upsert_member_earnings(conn, [("ai", "US", "2026-10-19", "NVDA", 0.55, "2026-Q2", "improved", 0.62, 0.03, "개선", "t1")])
    upsert_member_fcf(conn, [("ai", "US", "2026-10-19", "NVDA", 0.021, 0, "t2"), ("ai", "US", "2026-10-19", "AMD", None, None, "t2")])
    rows = dict((r[0], r[1:]) for r in conn.execute("SELECT ticker, rev_yoy, fcf_yield_3y, fcf_negative_years FROM theme_member_signals"))
    assert rows["NVDA"] == (0.55, 0.021, 0)
    assert rows["AMD"] == (None, None, None)
