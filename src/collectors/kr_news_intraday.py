"""한국 테마 뉴스 하루 세 번 수집 (2026-11-10, docs/radar/PROGRESS.md 2026-11-04).

## 왜

네이버 뉴스 검색은 날짜 검색이 없고 키워드마다 최신순 약 1000건까지만 넘길 수 있다. 예전에는 월요일 아침에
한 번 지난주 기사를 받았는데, 키워드 149개 중 51개가 한 주 1000건을 넘어(실측, probe_naver_saturation.py)
기사가 많은 테마일수록 다 못 셌다 - 'AI 반도체'는 주 약 1만 건인데 340건으로 셌다. 그래서 "뉴스는 조용"
판정(숨은 강세)을 믿을 수 없었다.

하루 기사량이 가장 많은 키워드도 하루 약 1400건이라, 8시간마다 "지난번에 읽은 데까지"만 받으면 한 번에
1000건 안에 든다. 받은 기사는 theme_news에 쌓고(테마·URL 기준으로 이미 중복이 막혀 있다) 주간 계산은 그 주에
쌓인 기사를 센다.

## 빈틈(gap)

실행이 크게 밀려 지난번 읽은 시점까지 닿기 전에 1000건이 차면 그 사이 기사를 놓친다. 그 키워드·주를
news_fetch_gaps에 남기고, 주간 계산은 그 테마의 그 주를 데이터부족(NULL)으로 둔다 - 덜 센 숫자가 가짜 "감소"로
보이면 안 된다(원칙 4). 처음 보는 키워드(테마 키워드 추가 등)도 그 주 앞부분을 못 읽었으니 빈틈으로 남긴다.

네트워크는 naver_fetch_since 하나만 탄다 - 나머지는 순수 함수라 시험할 수 있다.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests

from collectors.theme_news_collector import (FETCH_ATTEMPTS, FETCH_BACKOFF_SEC, NAVER_DISPLAY, NAVER_ENDPOINT,
                                             NAVER_MAX_START, _clean_naver_title, normalize_title)

OVERLAP = timedelta(hours=3)          # 지난번 읽은 시점보다 더 거슬러 읽는다 - 검색에 늦게 잡히는 기사 보호(중복은 DB가 막는다)
FIRST_LOOKBACK = timedelta(hours=14)  # 처음 보는 키워드는 이만큼만 - 그 주 앞부분은 빈틈으로 남긴다

NEWS_FETCH_STATE_DDL = """
CREATE TABLE IF NOT EXISTS news_fetch_state (
  market     TEXT NOT NULL,
  keyword    TEXT NOT NULL,
  last_seen  TEXT NOT NULL,     -- 지금까지 받은 가장 최신 기사 시각(ISO, UTC)
  updated_at TEXT NOT NULL,
  PRIMARY KEY (market, keyword)
)
"""

NEWS_FETCH_GAPS_DDL = """
CREATE TABLE IF NOT EXISTS news_fetch_gaps (
  market      TEXT NOT NULL,
  keyword     TEXT NOT NULL,
  week_start  TEXT NOT NULL,    -- 빈틈이 걸친 주(월요일)
  since       TEXT NOT NULL,    -- 여기까지 읽었어야 했는데
  reached     TEXT,             -- 실제로는 여기까지만 닿았다(NULL = 첫 수집)
  reason      TEXT NOT NULL,    -- 'capped' | 'first_fetch'
  recorded_at TEXT NOT NULL,
  PRIMARY KEY (market, keyword, week_start, since)
)
"""


def week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weeks_between(start: date, end: date) -> list[date]:
    """start-end(포함)가 걸친 주들의 월요일."""
    out, w = [], week_monday(start)
    while w <= end:
        out.append(w)
        w += timedelta(days=7)
    return out


def since_for(last_seen: str | None, now: datetime) -> tuple[datetime, bool]:
    """이번에 어디까지 거슬러 읽을지. 반환: (그 시각, 처음 보는 키워드인가)."""
    if last_seen:
        return datetime.fromisoformat(last_seen) - OVERLAP, False
    return now - FIRST_LOOKBACK, True


def naver_fetch_since(keyword: str, since: datetime, headers: dict, get=requests.get,
                      sleep=time.sleep) -> tuple[list[dict], bool, datetime | None]:
    """최신순으로 넘기며 since 이후 기사를 모은다. 반환: (기사, 상한에 막혀 since까지 못 닿았나, 가장 최신 기사 시각).

    기사 항목은 기존 수집과 같은 모양(title, url, published_at=날짜, source)에 '_published'(시각)를 더한다."""
    out: list[dict] = []
    newest: datetime | None = None
    start = 1
    while start <= NAVER_MAX_START:
        payload = None
        last_err: Exception | None = None
        for attempt in range(FETCH_ATTEMPTS):
            try:
                resp = get(NAVER_ENDPOINT, headers=headers, timeout=15,
                           params={"query": keyword, "display": NAVER_DISPLAY, "start": start, "sort": "date"})
                resp.raise_for_status()
                payload = resp.json()
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < len(FETCH_BACKOFF_SEC):
                    sleep(FETCH_BACKOFF_SEC[attempt])
        if payload is None:
            # 조회 실패를 0건으로 둔갑시키지 않는다 - 호출부가 그 키워드 상태를 갱신하지 않게 올린다.
            raise RuntimeError(f"네이버 조회 실패({keyword}): {type(last_err).__name__}")
        items = payload.get("items") or []
        reached = False
        for item in items:
            try:
                published = parsedate_to_datetime(item.get("pubDate") or "")
            except (ValueError, TypeError):
                continue
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if newest is None or published > newest:
                newest = published
            if published < since:
                reached = True
                break
            url = item.get("originallink") or item.get("link") or ""
            if not url:
                continue
            out.append({"title": _clean_naver_title(item.get("title", "")), "url": url,
                        "published_at": published.date().isoformat(), "source": urlparse(url).netloc,
                        "_published": published})
        if reached or len(items) < NAVER_DISPLAY:
            return out, False, newest
        start += NAVER_DISPLAY
        sleep(0.2)
    return out, True, newest


def count_unique_titles(titles: list[str]) -> int:
    """주간 건수 - 저장된 기사(이미 URL로 중복이 빠져 있다)에서 정규화한 제목이 같은 것을 한 번만 센다.

    한 번에 받던 시절에는 제목 유사도(90%+)까지 봤지만, 쌓인 기사가 테마·주당 수천 건이라 모든 쌍을 비교하면
    너무 느리다. 같은 제목의 재송고만 빼고 비슷한 제목은 따로 센다 - 세는 방식이 바뀌므로 기준선은 새로
    쌓는다(theme_signals.NEWS_SOURCE_SWITCH_WEEK)."""
    return len({normalize_title(t or "") for t in titles if (t or "").strip()})


# ── DB (테스트는 sqlite 메모리로) ─────────────────────────────────────────────

def ensure_intraday_schema(conn) -> None:
    conn.execute(NEWS_FETCH_STATE_DDL)
    conn.execute(NEWS_FETCH_GAPS_DDL)
    conn.commit()


def _record_gap(conn, market: str, keyword: str, since: datetime, reached: datetime | None,
                reason: str, now: datetime) -> list[str]:
    """since-reached 사이를 못 읽었다고 그 기간이 걸친 주마다 남긴다. 반환: 기록한 주."""
    end = (reached or now).date()
    weeks = [w.isoformat() for w in weeks_between(since.date(), end)]
    for w in weeks:
        conn.execute(
            "INSERT OR IGNORE INTO news_fetch_gaps (market, keyword, week_start, since, reached, reason, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (market, keyword, w, since.isoformat(), reached.isoformat() if reached else None, reason, now.isoformat()),
        )
    return weeks


def run_intraday(conn, themes: list[dict], headers: dict, now: datetime | None = None,
                 fetch=naver_fetch_since, insert=None, log=print) -> dict:
    """키워드마다 지난번 읽은 데까지 새 기사를 받아 테마별로 theme_news에 쌓는다.

    themes: [{"id", "keywords_ko"}]. 같은 키워드가 여러 테마에 있으면 한 번만 받는다.
    저장은 테마·URL 기준 중복만 뺀다(같은 제목은 셀 때 뺀다 - count_unique_titles). 조회에 실패한 키워드는
    상태를 갱신하지 않는다(다음 실행이 같은 시점부터 다시 읽는다)."""
    from collectors.theme_news_collector import hash_url
    if insert is None:
        try:
            from db.theme_signals import insert_theme_news_bulk as insert
        except ImportError:
            from src.db.theme_signals import insert_theme_news_bulk as insert
    now = now or datetime.now(timezone.utc)
    ensure_intraday_schema(conn)
    state = {r[0]: r[1] for r in conn.execute(
        "SELECT keyword, last_seen FROM news_fetch_state WHERE market = 'KR'").fetchall()}

    keywords = sorted({kw for t in themes for kw in (t.get("keywords_ko") or [])})
    by_keyword: dict[str, list[dict]] = {}
    stats = {"keywords": len(keywords), "fetched": 0, "capped": [], "first": [], "failed": []}
    for kw in keywords:
        since, first = since_for(state.get(kw), now)
        try:
            articles, capped, newest = fetch(kw, since, headers)
        except Exception as e:  # noqa: BLE001
            stats["failed"].append(f"{kw}: {type(e).__name__}")
            continue
        by_keyword[kw] = articles
        stats["fetched"] += len(articles)
        if first:
            # 처음 보는 키워드 - 이번 주 앞부분(월요일-since)을 못 읽었다
            _record_gap(conn, "KR", kw, datetime.combine(week_monday(since.date()), datetime.min.time(),
                                                           tzinfo=timezone.utc), since, "first_fetch", now)
            stats["first"].append(kw)
        if capped:
            oldest = min(a["_published"] for a in articles) if articles else None
            _record_gap(conn, "KR", kw, since, oldest, "capped", now)
            stats["capped"].append(kw)
        # 다음 실행의 출발점 = 지금까지 본 가장 최신 기사 시각(없으면 이전 값, 그것도 없으면 지금).
        prev = datetime.fromisoformat(state[kw]) if kw in state else None
        last = max([x for x in (newest, prev) if x is not None], default=now)
        conn.execute(
            "INSERT INTO news_fetch_state (market, keyword, last_seen, updated_at) VALUES ('KR', ?, ?, ?) "
            "ON CONFLICT(market, keyword) DO UPDATE SET last_seen = excluded.last_seen, updated_at = excluded.updated_at",
            (kw, last.isoformat(), now.isoformat()),
        )
        conn.commit()

    stored = 0
    for t in themes:
        seen: set[str] = set()
        per_week: dict[str, list[dict]] = {}
        for kw in t.get("keywords_ko") or []:
            for a in by_keyword.get(kw, []):
                h = hash_url(a["url"])
                if h in seen:
                    continue
                seen.add(h)
                per_week.setdefault(week_monday(date.fromisoformat(a["published_at"])).isoformat(), []).append(
                    {**{k: v for k, v in a.items() if k != "_published"}, "_url_hash": h})
        for week, items in per_week.items():
            insert(conn, t["id"], "KR", week, items)
            stored += len(items)
        conn.commit()
    stats["stored_attempts"] = stored
    log(f"[kr-intraday] 키워드 {stats['keywords']}개, 받은 기사 {stats['fetched']}건, 테마별 저장 시도 {stored}건"
        f" / 상한 {len(stats['capped'])} / 처음 {len(stats['first'])} / 실패 {len(stats['failed'])}")
    if stats["capped"]:
        log(f"[kr-intraday] 상한에 막혀 일부 못 읽은 키워드: {stats['capped']} - 그 주는 데이터부족으로 계산된다")
    return stats


def weekly_count(conn, theme_id: str, keywords: list[str], week_start: str) -> tuple[int | None, list[str]]:
    """그 주에 쌓인 기사 수(같은 제목 한 번). 그 테마 키워드에 빈틈이 있으면 (None, 빈틈 키워드)."""
    gaps = []
    if keywords:
        ph = ",".join("?" for _ in keywords)
        gaps = [r[0] for r in conn.execute(
            f"SELECT DISTINCT keyword FROM news_fetch_gaps WHERE market = 'KR' AND week_start = ? AND keyword IN ({ph})",
            (week_start, *keywords)).fetchall()]
    if gaps:
        return None, gaps
    titles = [r[0] for r in conn.execute(
        "SELECT title FROM theme_news WHERE theme_id = ? AND market = 'KR' AND week_start = ?",
        (theme_id, week_start)).fetchall()]
    return count_unique_titles(titles), []
