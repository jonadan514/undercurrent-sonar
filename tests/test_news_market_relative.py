"""미국 뉴스 화살표 시장 대비 판정 (src/db/theme_signals.py).

미국 뉴스는 소속 기업 뉴스 건수라 실적 발표 철에 테마와 무관하게 다 같이 늘어난다(2026-10-26 주 32개 중 22개 증가).
지키는 것:
  - 원래 비율(news_ratio)은 그대로 둔다 - 보고서·이력이 쓰는 값이다.
  - 비율이 없는 테마(na)를 화살표로 만들지 않는다(원칙 4).
  - 테마가 모자라면 시장 값을 믿을 수 없으니 판정을 바꾸지 않는다.
  - 여러 번 돌려도 같고, 한국에는 적용하지 않는다.
네트워크·운영 DB를 타지 않는다.
"""
from __future__ import annotations

import sqlite3

import pytest

from src.db.theme_signals import (NEWS_RELATIVE_MIN_THEMES, apply_market_relative_news, ensure_schema,
                                  market_relative_arrows, news_arrow_from_ratio, upsert_news_signal)

TH = {"strong_up": 2.0, "up": 1.3, "down": 0.7}
WEEK = "2026-10-26"


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    return conn


def _seed(conn, ratios: dict, market="US"):
    for theme, r in ratios.items():
        upsert_news_signal(conn, theme, market, WEEK, 100, 50.0, r, "na" if r is None else news_arrow_from_ratio(r, TH),
                           False, "t")
    conn.commit()


def _row(conn, theme, market="US"):
    return conn.execute("SELECT news_ratio, news_arrow, news_market_ratio, news_rel_ratio FROM theme_signals "
                        "WHERE theme_id = ? AND market = ? AND week_start = ?", (theme, market, WEEK)).fetchone()


def _ratios(n=11, value=1.6):
    return {f"t{i}": value for i in range(n)}


def test_다_같이_오른_주는_보합이_된다(db):
    _seed(db, _ratios())
    median, n = apply_market_relative_news(db, "US", WEEK, TH)
    assert median == pytest.approx(1.6) and n == 11
    assert _row(db, "t0")[1] == "flat"


def test_시장보다_더_오른_테마만_증가로_남는다(db):
    _seed(db, {**_ratios(), "hot": 3.4, "cold": 0.8})
    apply_market_relative_news(db, "US", WEEK, TH)
    assert _row(db, "hot")[1] == "up2"     # 3.4 / 1.6 = 2.1
    assert _row(db, "cold")[1] == "down"   # 0.8 / 1.6 = 0.5


def test_원래_비율은_바뀌지_않는다(db):
    _seed(db, _ratios())
    apply_market_relative_news(db, "US", WEEK, TH)
    ratio, _, market, rel = _row(db, "t0")
    assert ratio == pytest.approx(1.6) and market == pytest.approx(1.6) and rel == pytest.approx(1.0)


def test_비율이_없는_테마는_na_그대로(db):
    _seed(db, {**_ratios(), "empty": None})
    apply_market_relative_news(db, "US", WEEK, TH)
    assert _row(db, "empty") == (None, "na", None, None)


def test_테마가_모자라면_바꾸지_않는다(db):
    few = _ratios(NEWS_RELATIVE_MIN_THEMES - 1, 2.5)
    _seed(db, few)
    median, n = apply_market_relative_news(db, "US", WEEK, TH)
    assert median is None and n == 0
    assert _row(db, "t0")[1] == "up2"


def test_여러_번_돌려도_같다(db):
    _seed(db, {**_ratios(), "hot": 3.4})
    apply_market_relative_news(db, "US", WEEK, TH)
    first = _row(db, "hot")
    apply_market_relative_news(db, "US", WEEK, TH)
    assert _row(db, "hot") == first


def test_한국에는_적용하지_않는다(db):
    _seed(db, _ratios(), market="KR")
    assert apply_market_relative_news(db, "KR", WEEK, TH) == (None, 0)
    assert _row(db, "t0", "KR")[1] == "up1"


def test_중앙값이_0이하면_판정하지_않는다():
    assert market_relative_arrows({f"t{i}": 0.0 for i in range(11)}, TH) == (None, {})
