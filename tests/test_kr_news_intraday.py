"""한국 테마 뉴스 하루 세 번 수집 (src/collectors/kr_news_intraday.py).

지키는 것:
  - 지난번 읽은 시점(조금 겹쳐서)까지만 읽고 멈춘다 - 겹친 기사는 DB가 한 번만 넣는다.
  - 상한(1000건)에 막혀 그 시점까지 못 닿으면 빈틈으로 남기고, 그 주 건수는 데이터부족(NULL)이 된다(원칙 4).
  - 처음 보는 키워드는 그 주 앞부분을 못 읽었으니 빈틈이다.
  - 조회 실패는 0건으로 둔갑하지 않는다 - 상태를 그대로 둬 다음 실행이 같은 데서 다시 읽는다.
  - 주간 건수는 같은 제목을 한 번만 센다.
네이버는 가짜 응답으로, DB는 sqlite 메모리로 - 네트워크·운영 DB를 타지 않는다.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from collectors.kr_news_intraday import (FIRST_LOOKBACK, OVERLAP, count_unique_titles, naver_fetch_since,
                                         run_intraday, since_for, weekly_count, weeks_between)
from src.db.theme_signals import ensure_schema

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 18, 1, 20, tzinfo=timezone.utc)   # 수요일 10:20 KST


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def fake_naver(items_by_keyword: dict[str, list[datetime]]):
    """키워드별 기사 시각 목록(최신순으로 정렬해 준다)으로 네이버처럼 100건씩 돌려주는 가짜 get."""
    calls = []

    def get(url, headers=None, timeout=None, params=None):
        calls.append(params)
        stamps = sorted(items_by_keyword.get(params["query"], []), reverse=True)
        page = stamps[params["start"] - 1: params["start"] - 1 + params["display"]]
        return _Resp({"items": [{"title": f"{params['query']} 기사 {i + params['start']}",
                                 "originallink": f"https://news.example/{params['query']}/{t.isoformat()}",
                                 "pubDate": format_datetime(t)} for i, t in enumerate(page)]})
    get.calls = calls
    return get


def hourly(start: datetime, hours: int, per_hour: int = 1) -> list[datetime]:
    return [start + timedelta(hours=h, minutes=m * (60 // per_hour)) for h in range(hours) for m in range(per_hour)]


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    return conn


def _fetch_with(get):
    return lambda kw, since, headers: naver_fetch_since(kw, since, headers, get=get, sleep=lambda s: None)


THEMES = [{"id": "ai_semiconductor", "keywords_ko": ["HBM", "AI 반도체"]}]


# ── 순수 함수 ────────────────────────────────────────────────────────────────

def test_처음_보는_키워드는_짧게_거슬러_읽는다():
    since, first = since_for(None, NOW)
    assert first and since == NOW - FIRST_LOOKBACK


def test_이어_읽을_때는_지난번보다_조금_겹쳐서():
    last = NOW - timedelta(hours=8)
    since, first = since_for(last.isoformat(), NOW)
    assert not first and since == last - OVERLAP


def test_빈틈이_걸친_주를_모두_낸다():
    from datetime import date
    assert [w.isoformat() for w in weeks_between(date(2026, 11, 15), date(2026, 11, 17))] == ["2026-11-09", "2026-11-16"]


def test_같은_제목은_한_번만_센다():
    assert count_unique_titles(["HBM 공급 확대!", "HBM 공급 확대", "다른 기사", ""]) == 2


# ── 네이버 읽기 ──────────────────────────────────────────────────────────────

def test_since에_닿으면_멈춘다():
    get = fake_naver({"HBM": hourly(NOW - timedelta(hours=30), 30)})
    arts, capped, newest = naver_fetch_since("HBM", NOW - timedelta(hours=10), {}, get=get, sleep=lambda s: None)
    assert not capped and len(arts) == 10 and len(get.calls) == 1
    assert newest == max(hourly(NOW - timedelta(hours=30), 30))


def test_상한에_막히면_capped():
    """10분마다 기사 = 하루 144건 x 8일 > 1000건. 1000건을 넘겨도 since(8일 전)에 못 닿는다."""
    stamps = [NOW - timedelta(minutes=10 * i) for i in range(1, 1300)]
    arts, capped, _ = naver_fetch_since("AI 반도체", NOW - timedelta(days=8), {}, get=fake_naver({"AI 반도체": stamps}),
                                        sleep=lambda s: None)
    assert capped and len(arts) == 1000


# ── 하루 세 번 쌓기 ──────────────────────────────────────────────────────────

def test_두_번_나눠_받아도_같은_기사는_한_번만_쌓인다(db):
    stamps = {"HBM": hourly(NOW - timedelta(hours=40), 40), "AI 반도체": []}
    get = fake_naver(stamps)
    run_intraday(db, THEMES, {}, now=NOW - timedelta(hours=8), fetch=_fetch_with(get), log=lambda m: None)
    run_intraday(db, THEMES, {}, now=NOW, fetch=_fetch_with(get), log=lambda m: None)
    n = db.execute("SELECT COUNT(*) FROM theme_news WHERE theme_id = 'ai_semiconductor'").fetchone()[0]
    # 첫 실행: 처음 보는 키워드라 14시간 전부터 / 두 번째: 이어서(3시간 겹침) - 겹친 기사는 한 번만
    expected = len([t for t in stamps["HBM"] if t >= NOW - timedelta(hours=8) - FIRST_LOOKBACK])
    assert n == expected


def test_처음_보는_키워드와_상한은_빈틈으로_남아_그_주는_데이터부족(db):
    stamps = [NOW - timedelta(seconds=40 * i) for i in range(1, 1500)]   # 40초마다 = 14시간에 1260건 > 1000
    get = fake_naver({"HBM": stamps, "AI 반도체": []})
    stats = run_intraday(db, THEMES, {}, now=NOW, fetch=_fetch_with(get), log=lambda m: None)
    assert set(stats["first"]) == {"HBM", "AI 반도체"} and stats["capped"] == ["HBM"]
    count, gaps = weekly_count(db, "ai_semiconductor", ["HBM", "AI 반도체"], "2026-11-16")
    assert count is None and set(gaps) == {"HBM", "AI 반도체"}


def test_빈틈_없는_주는_쌓인_기사를_센다(db):
    db.execute("INSERT INTO theme_news (theme_id, market, url_hash, title, url, published_at, source, week_start) "
               "VALUES ('ai_semiconductor', 'KR', 'a', 'HBM 기사', 'u1', '2026-11-23', 's', '2026-11-23'), "
               "('ai_semiconductor', 'KR', 'b', 'HBM 기사', 'u2', '2026-11-23', 's', '2026-11-23'), "
               "('ai_semiconductor', 'KR', 'c', '다른 기사', 'u3', '2026-11-24', 's', '2026-11-23')")
    from collectors.kr_news_intraday import ensure_intraday_schema
    ensure_intraday_schema(db)
    assert weekly_count(db, "ai_semiconductor", ["HBM"], "2026-11-23") == (2, [])


def test_조회_실패는_상태를_건드리지_않는다(db):
    def boom(kw, since, headers):
        raise RuntimeError("down")
    stats = run_intraday(db, THEMES, {}, now=NOW, fetch=boom, log=lambda m: None)
    assert len(stats["failed"]) == 2
    assert db.execute("SELECT COUNT(*) FROM news_fetch_state").fetchone()[0] == 0
