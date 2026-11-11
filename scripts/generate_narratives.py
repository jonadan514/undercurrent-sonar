"""워치리스트 네러티브 브리프 생성 — 일간 파이프라인에서 실행.

워치리스트 후보 + 내 워치리스트 종목별로:
  1. 최근 7일 뉴스 헤드라인 수집 (Yahoo/Google News RSS, KR은 한국어 검색)
  2. GPT-4o mini가 투자 스토리·촉매·리스크·시장 관심도를 JSON으로 요약
  3. Turso narrative_briefs 테이블에 upsert (프론트엔드가 읽음)

2026-11-11부터 화면은 관심도(HOT/WARM/COLD)와 그 전환만 보여 준다 - 스토리·촉매·리스크 문장은 회사가 달라도
거의 같은 상투적 문장이라 뺐다. 생성 지침은 그대로 둔다: 관심도 상승이 신호 기록(sentiment_heating)으로
4주·12주 결과를 재는 중이라, 지침을 바꾸면 그 앞뒤 값이 다른 잣대가 된다.

사용:
  python scripts/generate_narratives.py                  # 기본 (7일 내 갱신분은 건너뜀)
  python scripts/generate_narratives.py --force          # 전부 재생성
  python scripts/generate_narratives.py --limit 5        # 테스트용
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db.turso_http import get_credentials, query as turso_query, execute_many as turso_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MAX_AGE_HOURS = 168         # 이보다 최신인 브리프는 건너뜀 (주 1회 크론 대비 — 7일)
OPENAI_MODEL = "gpt-4o-mini"


def _require_turso() -> None:
    if not get_credentials():
        logger.error("TURSO_DATA_URL / TURSO_DATA_TOKEN 미설정")
        sys.exit(1)


# ── 뉴스 수집 ───────────────────────────────────────────────────────────────

def collect_news(market: str, symbol: str, name: str | None) -> list[dict]:
    if market == "KR":
        return _google_news_kr(name or symbol)
    from src.analyzers.ai_summary_generator import NewsCollector
    return NewsCollector().get_news_for_ticker(symbol, name)


def _google_news_kr(name: str, limit: int = 6) -> list[dict]:
    """한국 종목: 구글 뉴스 한국어 RSS 검색."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    from urllib.parse import quote

    try:
        query = f'"{name}" 주가 OR 실적'
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            root = ET.fromstring(resp.read())

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        results = []
        for item in root.iter("item"):
            if len(results) >= limit:
                break
            pub_date = ""
            pub_el = item.find("pubDate")
            if pub_el is not None and pub_el.text:
                try:
                    dt = parsedate_to_datetime(pub_el.text)
                    if dt < cutoff:
                        continue
                    pub_date = dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    pass
            title_el = item.find("title")
            link_el = item.find("link")
            source_el = item.find("source")
            results.append({
                "title": title_el.text if title_el is not None else "",
                "publisher": source_el.text if source_el is not None else "",
                "link": link_el.text if link_el is not None else "",
                "published": pub_date,
                "source": "GoogleKR",
            })
        return results
    except Exception:
        logger.debug("%s KR 뉴스 수집 실패", name, exc_info=True)
        return []


# ── GPT-4o mini 네러티브 생성 ───────────────────────────────────────────────

NO_NEWS_BRIEF = {
    "story": "최근 1주일간 주요 뉴스가 수집되지 않았습니다. 시장의 관심 밖에 있는 시기일 수 있습니다.",
    "catalysts": [],
    "risks": [],
    "sentiment": "COLD",
    "sentiment_reason": "최근 7일 뉴스 없음",
}


def generate_brief(market: str, symbol: str, name: str | None, news: list[dict]) -> dict | None:
    """뉴스 헤드라인 기반 네러티브 JSON 생성. 실패 시 None."""
    if not news:
        return {**NO_NEWS_BRIEF, "sources": []}

    import requests

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.error("OPENAI_API_KEY 미설정")
        sys.exit(1)

    headlines = "\n".join(
        f"- [{n.get('published','?')}] {n.get('title','')} ({n.get('publisher','')})"
        for n in news
    )
    market_label = "한국(KOSPI/KOSDAQ)" if market == "KR" else "미국(NYSE/NASDAQ)"
    prompt = f"""종목: {name or symbol} (티커/코드: {symbol}, {market_label} 상장)

아래는 이 종목의 최근 1주일 뉴스 헤드라인입니다:
{headlines}

이 종목은 1~3년 보유를 전제로 한 펀더멘털 투자 후보입니다. 헤드라인을 바탕으로 이 종목의
장기 투자 스토리를 분석해 아래 JSON 형식으로만 답하세요. 헤드라인에 없는 내용을 지어내지 마세요.

{{
  "story": "핵심 투자 스토리 2~3문장 — 이 회사의 장기 성장 동력/사업 구조가 왜 매력적인지(또는 우려되는지)",
  "catalysts": ["앞으로 1~3년 스토리에 영향을 줄 요인 최대 3개 (구조적 성장동력·신사업·정책 변화·업황 전환 등. 단기 실적발표 같은 이벤트도 있으면 포함 가능하나 우선순위는 아님)"],
  "risks": ["이 장기 스토리가 깨질 수 있는 근본적 리스크 최대 3개"],
  "sentiment": "HOT 또는 WARM 또는 COLD",
  "sentiment_reason": "시장의 단기 관심도 판단 근거 한 문장 (참고용 — 장기 투자 판단의 핵심 지표는 아님)"
}}

sentiment은 "시장 단기 관심도"를 뜻하는 보조 정보일 뿐입니다: HOT=뉴스가 많고 시장이 활발히
이야기하는 인기 테마, WARM=꾸준한 관심, COLD=뉴스가 적거나 관심 밖. 장기 투자 스토리(story)의
매력도와는 별개이니 혼동하지 마세요 — 관심 밖(COLD)이어도 장기 스토리는 탄탄할 수 있습니다.
모든 내용은 한국어로 작성하세요."""

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": "당신은 주식 시장 네러티브 분석가입니다. 반드시 유효한 JSON만 출력합니다."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 700,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(text)
        if not isinstance(parsed.get("story"), str):
            return None
        sentiment = parsed.get("sentiment", "WARM")
        if sentiment not in ("HOT", "WARM", "COLD"):
            sentiment = "WARM"
        return {
            "story": parsed["story"],
            "catalysts": (parsed.get("catalysts") or [])[:3],
            "risks": (parsed.get("risks") or [])[:3],
            "sentiment": sentiment,
            "sentiment_reason": parsed.get("sentiment_reason", ""),
            "sources": [n["link"] for n in news if n.get("link")][:5],
        }
    except Exception as e:
        logger.warning("%s GPT 요약 실패: %s", symbol, type(e).__name__)
        return None


# ── main ───────────────────────────────────────────────────────────────────

CREATE_SQL = (
    "CREATE TABLE IF NOT EXISTS narrative_briefs ("
    "  market TEXT NOT NULL,"
    "  symbol TEXT NOT NULL,"
    "  payload TEXT NOT NULL,"
    "  updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
    "  PRIMARY KEY (market, symbol)"
    ")"
)

UPSERT_SQL = (
    "INSERT INTO narrative_briefs (market, symbol, payload, updated_at) "
    "VALUES (?, ?, ?, datetime('now')) "
    "ON CONFLICT(market, symbol) DO UPDATE SET "
    "payload=excluded.payload, updated_at=excluded.updated_at"
)

# 관심도(sentiment) 일별 이력 — COLD→WARM→HOT 전환 감지용
HISTORY_CREATE_SQL = (
    "CREATE TABLE IF NOT EXISTS narrative_sentiment_history ("
    "  market TEXT NOT NULL,"
    "  symbol TEXT NOT NULL,"
    "  date TEXT NOT NULL,"
    "  sentiment TEXT NOT NULL,"
    "  PRIMARY KEY (market, symbol, date)"
    ")"
)

HISTORY_INSERT_SQL = (
    "INSERT INTO narrative_sentiment_history (market, symbol, date, sentiment) "
    "VALUES (?, ?, ?, ?) "
    "ON CONFLICT(market, symbol, date) DO UPDATE SET sentiment=excluded.sentiment"
)

SENTIMENT_RANK = {"COLD": 0, "WARM": 1, "HOT": 2}


def get_prior_sentiment(market: str, symbol: str, today: str) -> str | None:
    """오늘 이전 가장 최근 기록된 관심도. 없으면 None (첫 기록)."""
    rows = turso_query(
        "SELECT sentiment FROM narrative_sentiment_history "
        "WHERE market = ? AND symbol = ? AND date < ? "
        "ORDER BY date DESC LIMIT 1",
        [market, symbol, today],
    )
    return rows[0]["sentiment"] if rows else None


def compute_trend(prev: str | None, current: str) -> str | None:
    if prev is None or prev not in SENTIMENT_RANK:
        return None
    cur_rank, prev_rank = SENTIMENT_RANK.get(current, 1), SENTIMENT_RANK[prev]
    if cur_rank > prev_rank:
        return "up"
    if cur_rank < prev_rank:
        return "down"
    return "flat"


def get_todo(max_age_hours: int, batch: int, force: bool) -> tuple[list[dict], int]:
    """생성 대상 종목 결정.

    - 내 워치리스트: 항상 최우선 (매일 갱신)
    - 스크리닝 후보: 브리프가 없거나 오래된 것부터, 회차당 batch개까지 순환
    반환: (todo 리스트, 전체 대상 수)
    """
    my_rows = turso_query("SELECT market, symbol, name FROM my_watchlist")
    cand_rows = turso_query("SELECT market, symbol, name FROM watchlist_candidates")

    updated: dict[str, str] = {}
    for r in turso_query("SELECT market, symbol, updated_at FROM narrative_briefs"):
        updated[f"{r['market']}:{r['symbol']}"] = r["updated_at"] or ""

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).strftime("%Y-%m-%d %H:%M:%S")

    def is_stale(t: dict) -> bool:
        if force:
            return True
        return updated.get(f"{t['market']}:{t['symbol']}", "") < cutoff

    seen: set[str] = set()
    my_todo, cand_todo = [], []
    for t in my_rows:
        key = f"{t['market']}:{t['symbol']}"
        seen.add(key)
        if is_stale(t):
            my_todo.append(t)
    for t in cand_rows:
        key = f"{t['market']}:{t['symbol']}"
        if key not in seen and is_stale(t):
            cand_todo.append(t)

    # 후보는 오래된(또는 브리프 없는) 순으로 — 매 회차 다른 종목이 갱신되며 순환
    cand_todo.sort(key=lambda t: updated.get(f"{t['market']}:{t['symbol']}", ""))
    todo = my_todo + cand_todo
    if batch > 0:
        todo = todo[:batch]
    return todo, len(my_rows) + len(cand_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="워치리스트 네러티브 브리프 생성")
    parser.add_argument("--limit", type=int, default=0, help="처리 종목 수 제한 (0=배치 기본값)")
    parser.add_argument("--batch", type=int, default=400, help="회차당 최대 생성 수 (기본 400 — 상위 50 캡 제거로 후보 풀이 커짐)")
    parser.add_argument("--force", action="store_true", help="신선도 무시하고 전부 재생성")
    args = parser.parse_args()

    _require_turso()
    t0 = time.time()
    turso_pipeline([
        (CREATE_SQL, None),
        (HISTORY_CREATE_SQL, None),
    ])

    batch = args.limit if args.limit > 0 else args.batch
    todo, total = get_todo(MAX_AGE_HOURS, batch, args.force)
    if not todo:
        logger.info("생성할 종목 없음 (전체 %d종목 모두 신선)", total)
        return

    logger.info("전체 %d종목 중 이번 회차 %d종목 생성", total, len(todo))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ok = fail = 0
    for i, t in enumerate(todo, 1):
        market, symbol, name = t["market"], t["symbol"], t.get("name")
        news = collect_news(market, symbol, name)
        brief = generate_brief(market, symbol, name, news)
        if brief is None:
            fail += 1
            continue

        prev_sentiment = get_prior_sentiment(market, symbol, today)
        trend = compute_trend(prev_sentiment, brief["sentiment"])
        brief["prev_sentiment"] = prev_sentiment
        brief["trend"] = trend  # up/down/flat/None(첫 기록)
        brief["name"] = name    # 표시용 (KR은 코드만으론 식별 어려움)

        turso_pipeline([
            (UPSERT_SQL, [market, symbol, json.dumps(brief, ensure_ascii=False)]),
            (HISTORY_INSERT_SQL, [market, symbol, today, brief["sentiment"]]),
        ])
        ok += 1
        trend_note = f" ({prev_sentiment}→{brief['sentiment']})" if trend == "up" else ""
        logger.info("[%d/%d] %s(%s) %s 뉴스%d건%s", i, len(todo), symbol, market,
                    brief["sentiment"], len(news), trend_note)
        time.sleep(0.3)  # API 예의

    logger.info("완료: 성공 %d / 실패 %d / 소요 %.1f초", ok, fail, time.time() - t0)


if __name__ == "__main__":
    main()
