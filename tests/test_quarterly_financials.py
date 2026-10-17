"""분기 재무 저장·선택 규칙 (작업지시서 Phase 6 / docs/REDESIGN_SPEC.md 4-4).

핵심 규칙
  - 수집값은 쌓는다(덮어쓰지 않는다)
  - 읽을 때 연결재무(CFS)를 먼저 고르고, 없으면 별도재무(OFS)
  - 같은 구분이면 나중에 수집한 값(정정공시 반영)
"""
from __future__ import annotations

import pytest

from src.db.quarterly_financials import (ensure_schema, insert_quarter, migrate_legacy_rows,
                                          select_quarters, select_quarters_bulk)


def put(conn, *, year=2026, quarter=2, fs="CFS", revenue=100, op=10, net=5,
        on="2026-09-20", source="DART", ticker="005930", market="KR", derived="reported"):
    insert_quarter(conn, ticker, market, year, quarter,
                   {"revenue": revenue, "operating_income": op, "net_income": net,
                    "fs_div": fs, "derived": derived},
                   source, "KRW", f"{on}T00:00:00")
    conn.commit()


def test_넣은_값을_그대로_읽는다(memory_db):
    ensure_schema(memory_db)
    put(memory_db, revenue=1234, op=56, net=78)
    rows = select_quarters(memory_db, "005930", "KR")
    assert len(rows) == 1
    assert (rows[0]["revenue"], rows[0]["operating_income"], rows[0]["net_income"]) == (1234, 56, 78)
    assert rows[0]["fs_div"] == "CFS" and rows[0]["source"] == "DART"


def test_별도재무로_먼저_저장돼도_나중에_연결재무가_들어오면_연결을_쓴다(memory_db):
    """이게 Phase 6이 고치는 버그다. 전에는 먼저 들어온 별도재무가 그대로 남았다."""
    ensure_schema(memory_db)
    put(memory_db, fs="OFS", revenue=100, on="2026-09-01")
    put(memory_db, fs="CFS", revenue=130, on="2026-09-20")
    rows = select_quarters(memory_db, "005930", "KR")
    assert len(rows) == 1, "분기 하나에 값 하나만 골라야 한다"
    assert rows[0]["fs_div"] == "CFS" and rows[0]["revenue"] == 130


def test_연결재무가_먼저였으면_나중에_별도가_들어와도_연결을_지킨다(memory_db):
    ensure_schema(memory_db)
    put(memory_db, fs="CFS", revenue=130, on="2026-09-01")
    put(memory_db, fs="OFS", revenue=100, on="2026-09-20")
    assert select_quarters(memory_db, "005930", "KR")[0]["revenue"] == 130


def test_같은_구분이면_나중에_수집한_값을_쓴다(memory_db):
    """정정공시로 숫자가 바뀌는 경우."""
    ensure_schema(memory_db)
    put(memory_db, fs="CFS", revenue=100, on="2026-09-01")
    put(memory_db, fs="CFS", revenue=111, on="2026-09-20")
    assert select_quarters(memory_db, "005930", "KR")[0]["revenue"] == 111


def test_예전_값도_지우지_않고_남긴다(memory_db):
    ensure_schema(memory_db)
    put(memory_db, fs="OFS", revenue=100, on="2026-09-01")
    put(memory_db, fs="CFS", revenue=130, on="2026-09-20")
    kept = memory_db.execute("SELECT COUNT(*) FROM quarterly_financials_raw").fetchone()[0]
    assert kept == 2, "원본은 둘 다 남아 있어야 한다(원칙 5)"


def test_같은_날_같은_구분으로_다시_수집하면_그_행만_갱신된다(memory_db):
    ensure_schema(memory_db)
    put(memory_db, fs="CFS", revenue=100, on="2026-09-20")
    put(memory_db, fs="CFS", revenue=105, on="2026-09-20")
    n = memory_db.execute("SELECT COUNT(*) FROM quarterly_financials_raw").fetchone()[0]
    assert n == 1 and select_quarters(memory_db, "005930", "KR")[0]["revenue"] == 105


def test_분기는_최신순으로_돌려준다(memory_db):
    ensure_schema(memory_db)
    for y, q in [(2025, 3), (2026, 1), (2025, 4), (2026, 2)]:
        put(memory_db, year=y, quarter=q)
    got = [(r["fiscal_year"], r["fiscal_quarter"]) for r in select_quarters(memory_db, "005930", "KR")]
    assert got == [(2026, 2), (2026, 1), (2025, 4), (2025, 3)]


def test_다른_기업_시장은_섞이지_않는다(memory_db):
    ensure_schema(memory_db)
    put(memory_db, ticker="005930", market="KR", revenue=100)
    put(memory_db, ticker="NVDA", market="US", revenue=900)
    assert select_quarters(memory_db, "NVDA", "US")[0]["revenue"] == 900
    assert len(select_quarters(memory_db, "005930", "KR")) == 1


def test_구분이_없는_출처도_저장된다(memory_db):
    """yfinance는 연결·별도 구분이 없다."""
    ensure_schema(memory_db)
    put(memory_db, ticker="NVDA", market="US", fs=None, source="yfinance", revenue=900)
    row = select_quarters(memory_db, "NVDA", "US")[0]
    assert row["fs_div"] == "NA" and row["revenue"] == 900


def test_공시_원본이_있으면_나중에_받은_yfinance보다_공시를_쓴다(memory_db):
    """2026-10-17: 같은 분기에 SEC·yfinance 행이 둘 다 있으면 수집 순서와 상관없이 SEC."""
    ensure_schema(memory_db)
    put(memory_db, ticker="MU", market="US", fs=None, source="SEC", revenue=11315, op=3654, on="2026-10-17")
    put(memory_db, ticker="MU", market="US", fs=None, source="yfinance", revenue=11315, op=3693, on="2026-10-24")
    row = select_quarters(memory_db, "MU", "US")[0]
    assert row["source"] == "SEC" and row["operating_income"] == 3654


def test_공시_원본이_없는_분기는_yfinance를_쓰고_공시끼리는_늦은_값(memory_db):
    ensure_schema(memory_db)
    put(memory_db, ticker="MU", market="US", fs=None, source="yfinance", year=2026, quarter=3, revenue=54000)
    put(memory_db, ticker="MU", market="US", fs=None, source="SEC", year=2026, quarter=2, revenue=41000, on="2026-10-01")
    put(memory_db, ticker="MU", market="US", fs=None, source="SEC", year=2026, quarter=2, revenue=41456, on="2026-10-17")
    rows = select_quarters(memory_db, "MU", "US")
    assert (rows[0]["fiscal_quarter"], rows[0]["source"]) == (3, "yfinance")
    assert (rows[1]["source"], rows[1]["revenue"]) == ("SEC", 41456)   # 정정 반영


# ── 예전 테이블 이전 ──────────────────────────────────────────

def _legacy_row(conn, **kw):
    conn.execute(
        "INSERT INTO quarterly_financials (ticker, market, fiscal_year, fiscal_quarter, revenue,"
        " operating_income, net_income, source, fs_div, derived, currency, collected_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (kw.get("ticker", "005930"), "KR", 2026, 2, kw.get("revenue", 100), 10, 5,
         "DART", kw.get("fs", "OFS"), "reported", "KRW", "2026-09-18T01:00:00"))
    conn.commit()


def test_예전_테이블_값을_raw로_옮긴다(memory_db):
    ensure_schema(memory_db)
    _legacy_row(memory_db, revenue=100)
    migrate_legacy_rows(memory_db)
    rows = select_quarters(memory_db, "005930", "KR")
    assert len(rows) == 1 and rows[0]["revenue"] == 100 and rows[0]["fs_div"] == "OFS"


def test_이전을_두_번_돌려도_중복되지_않는다(memory_db):
    ensure_schema(memory_db)
    _legacy_row(memory_db)
    migrate_legacy_rows(memory_db)
    migrate_legacy_rows(memory_db)
    n = memory_db.execute("SELECT COUNT(*) FROM quarterly_financials_raw").fetchone()[0]
    assert n == 1


def test_옮긴_뒤_연결재무를_새로_받으면_그것을_쓴다(memory_db):
    """이전 데이터(별도) + 새 수집(연결) -> 연결이 이긴다."""
    ensure_schema(memory_db)
    _legacy_row(memory_db, fs="OFS", revenue=100)
    migrate_legacy_rows(memory_db)
    put(memory_db, fs="CFS", revenue=130, on="2026-09-21")
    assert select_quarters(memory_db, "005930", "KR")[0]["revenue"] == 130


# ── 운영 DB(Turso) 반환 타입 ──────────────────────────────────
#
# Turso는 INTEGER 컬럼을 문자열로 돌려준다. 로컬 sqlite만으로 테스트하면 이 차이가 드러나지
# 않아, 다음 단계(변화 신호 계산)가 `연도 - 1`이나 `분기 == 4`를 할 때 운영에서만 틀린다.

def test_운영DB에서도_연도와_분기가_숫자다(turso_like_db):
    ensure_schema(turso_like_db)
    put(turso_like_db, year=2026, quarter=2, revenue=1_000_000)
    row = select_quarters(turso_like_db, "005930", "KR")[0]
    assert row["fiscal_year"] == 2026 and row["fiscal_quarter"] == 2
    assert isinstance(row["fiscal_year"], int) and isinstance(row["fiscal_quarter"], int)


def test_운영DB에서도_금액이_숫자다(turso_like_db):
    ensure_schema(turso_like_db)
    put(turso_like_db, revenue=1_234_500, op=100, net=50)
    row = select_quarters(turso_like_db, "005930", "KR")[0]
    assert row["revenue"] == pytest.approx(1_234_500)
    assert isinstance(row["revenue"], float) and isinstance(row["operating_income"], float)


def test_운영DB에서_직전_분기_계산이_된다(turso_like_db):
    """변화 신호가 쓰는 '1년 전 같은 분기' 찾기 - 문자열이면 여기서 깨진다."""
    ensure_schema(turso_like_db)
    for y, q in [(2026, 2), (2026, 1), (2025, 4), (2025, 3), (2025, 2)]:
        put(turso_like_db, year=y, quarter=q, revenue=100 + q)
    rows = select_quarters(turso_like_db, "005930", "KR")
    latest = rows[0]
    year_ago = (latest["fiscal_year"] - 1, latest["fiscal_quarter"])
    assert year_ago == (2025, 2)
    assert any((r["fiscal_year"], r["fiscal_quarter"]) == year_ago for r in rows)


def test_운영DB에서도_연결재무_우선이_동작한다(turso_like_db):
    ensure_schema(turso_like_db)
    put(turso_like_db, fs="OFS", revenue=100, on="2026-09-01")
    put(turso_like_db, fs="CFS", revenue=130, on="2026-09-20")
    row = select_quarters(turso_like_db, "005930", "KR")[0]
    assert row["fs_div"] == "CFS" and row["revenue"] == pytest.approx(130)


def test_운영DB에서도_최신순_정렬이_맞다(turso_like_db):
    ensure_schema(turso_like_db)
    for y, q in [(2025, 3), (2026, 10 - 9), (2025, 4), (2026, 2)]:
        put(turso_like_db, year=y, quarter=q)
    got = [(r["fiscal_year"], r["fiscal_quarter"]) for r in select_quarters(turso_like_db, "005930", "KR")]
    assert got == [(2026, 2), (2026, 1), (2025, 4), (2025, 3)]


def test_금액이_없는_분기도_읽을_수_있다(turso_like_db):
    """계산 불가를 탈락으로 처리하지 않는다(원칙 4) - None이 그대로 와야 한다."""
    ensure_schema(turso_like_db)
    put(turso_like_db, revenue=None, op=None, net=None)
    row = select_quarters(turso_like_db, "005930", "KR")[0]
    assert row["revenue"] is None and row["operating_income"] is None


# ── 이전 행 수 (검토 지적 D) ──────────────────────────────────
#
# 운영 DB는 execute()가 커서가 아니라 자기 자신을 돌려주고 rowcount가 없다. 예전 구현은
# rowcount를 읽어서 실제로 몇 행을 옮겼어도 운영에서는 항상 0을 돌려줬고, 그 값으로 찍는
# 로그가 "이전이 돌았는지"를 알려주지 못했다.

def test_운영DB에서_옮긴_행_수를_돌려준다(turso_like_db):
    ensure_schema(turso_like_db)
    _legacy_row(turso_like_db, ticker="005930")
    _legacy_row(turso_like_db, ticker="000660")
    assert migrate_legacy_rows(turso_like_db) == 2


def test_운영DB에서_이미_옮긴_행은_세지_않는다(turso_like_db):
    ensure_schema(turso_like_db)
    _legacy_row(turso_like_db, ticker="005930")
    _legacy_row(turso_like_db, ticker="000660")
    migrate_legacy_rows(turso_like_db)
    assert migrate_legacy_rows(turso_like_db) == 0


def test_운영DB에서_돌려준_행_수는_정수다(turso_like_db):
    """Turso는 COUNT(*)도 문자열로 돌려준다 - 정수로 바꾸지 않으면 뺄셈에서 죽는다."""
    ensure_schema(turso_like_db)
    _legacy_row(turso_like_db)
    got = migrate_legacy_rows(turso_like_db)
    assert isinstance(got, int) and got == 1


def test_옮길_행이_없으면_0이다(turso_like_db):
    ensure_schema(turso_like_db)
    assert migrate_legacy_rows(turso_like_db) == 0


def test_로컬_sqlite에서도_옮긴_행_수가_맞다(memory_db):
    ensure_schema(memory_db)
    _legacy_row(memory_db, ticker="005930")
    _legacy_row(memory_db, ticker="000660")
    assert migrate_legacy_rows(memory_db) == 2
    assert migrate_legacy_rows(memory_db) == 0


# ── 여러 종목 한 번에 조회 (select_quarters_bulk) ──────────────
#
# 분기 4칸 분류 실행 스크립트가 테마 소속 기업·유니버스 전체를 한 번의 쿼리로
# 묶어 조회할 때 쓴다 - 종목마다 select_quarters()를 부르면 운영 DB(Turso HTTP)에
# 종목 수만큼 왕복이 쌓인다.

def test_여러_종목을_한번에_읽는다(memory_db):
    ensure_schema(memory_db)
    put(memory_db, ticker="005930", market="KR", revenue=100)
    put(memory_db, ticker="000660", market="KR", revenue=200)
    got = select_quarters_bulk(memory_db, ["005930", "000660"], "KR")
    assert got["005930"][0]["revenue"] == 100
    assert got["000660"][0]["revenue"] == 200


def test_여러_종목_결과가_개별_조회와_같다(memory_db):
    ensure_schema(memory_db)
    put(memory_db, fs="OFS", revenue=100, on="2026-09-01")
    put(memory_db, fs="CFS", revenue=130, on="2026-09-20")
    put(memory_db, ticker="000660", revenue=999, year=2025, quarter=4)
    bulk = select_quarters_bulk(memory_db, ["005930", "000660"], "KR")
    assert bulk["005930"] == select_quarters(memory_db, "005930", "KR")
    assert bulk["000660"] == select_quarters(memory_db, "000660", "KR")


def test_행이_없는_종목은_결과에서_빠진다(memory_db):
    """select_quarters()가 빈 리스트를 돌려주는 것과 같게, 호출부가 .get(t, [])로 다뤄야 한다."""
    ensure_schema(memory_db)
    put(memory_db, ticker="005930")
    got = select_quarters_bulk(memory_db, ["005930", "999999"], "KR")
    assert "999999" not in got
    assert got.get("999999", []) == []


def test_빈_티커_목록이면_빈_딕셔너리다(memory_db):
    ensure_schema(memory_db)
    assert select_quarters_bulk(memory_db, [], "KR") == {}


def test_다른_시장_종목은_섞이지_않는다(memory_db):
    ensure_schema(memory_db)
    put(memory_db, ticker="005930", market="KR", revenue=100)
    put(memory_db, ticker="005930", market="US", revenue=900)   # 같은 티커, 다른 시장(우연)
    got = select_quarters_bulk(memory_db, ["005930"], "KR")
    assert got["005930"][0]["revenue"] == 100


def test_운영DB에서도_여러_종목_조회가_맞다(turso_like_db):
    ensure_schema(turso_like_db)
    put(turso_like_db, ticker="005930", revenue=100, op=10)
    put(turso_like_db, ticker="000660", revenue=200, op=20)
    got = select_quarters_bulk(turso_like_db, ["005930", "000660"], "KR")
    assert got["005930"][0]["revenue"] == 100.0 and isinstance(got["005930"][0]["revenue"], float)
    assert got["005930"][0]["fiscal_year"] == 2026 and isinstance(got["005930"][0]["fiscal_year"], int)
    assert got["000660"][0]["revenue"] == 200.0


def test_운영DB에서도_연결재무_우선이_여러_종목_조회에서도_동작한다(turso_like_db):
    ensure_schema(turso_like_db)
    put(turso_like_db, ticker="005930", fs="OFS", revenue=100, on="2026-09-01")
    put(turso_like_db, ticker="005930", fs="CFS", revenue=130, on="2026-09-20")
    got = select_quarters_bulk(turso_like_db, ["005930"], "KR")
    assert got["005930"][0]["fs_div"] == "CFS" and got["005930"][0]["revenue"] == 130.0
