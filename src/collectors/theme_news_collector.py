"""Phase A-3/B-1: 테마 키워드 기반 뉴스 수집 (Google News RSS).

SPEC: docs/radar/SPEC_phase_a_signals.md §2
Phase A는 미국 시장만 대상이었으나(keywords_en), Phase B에서 한국어 검색
(keywords_ko)을 추가한다 - normalize_title()이 애초에 한글 범위(가-힣)를
포함하고 있어 이 확장을 이미 염두에 두고 설계돼 있었다.

키워드별로 따로 검색해서 합친 뒤 중복 제거한다(§3 논의에서 정한 "옵션 B") -
어떤 키워드가 건수를 과도하게 밀어올리는지 나중에 진단할 수 있어야 하기 때문
(SPEC §8 "특정 테마만 계속 up2 -> 키워드가 너무 넓음" 진단과 직결).
"""
from __future__ import annotations

import hashlib
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlparse, urlunparse

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# Google News RSS는 공식 요율제한 문서가 없는 비공식에 가까운 엔드포인트다.
# 키워드별로 따로 검색하면 요청 수가 늘어나므로(테마당 키워드 수 x 8주 백필 시
# 수백 건), Phase 0의 yfinance 요율제한 사고를 반복하지 않기 위한 안전장치.
KEYWORD_SLEEP_SEC = 1.0

# Google News RSS는 한 요청에 최대 100건만 준다 - 2026-09-17 실측: &num=200을 붙여도,
# 기간을 하루로 좁히거나 분기로 넓혀도 똑같이 100건이 상한이다. 즉 인기 키워드는 실제
# 기사가 몇 백 건이든 100건으로 잘려 세어진다(주간 실행에서 키워드-주 조합의 16%가 상한).
# 대응: 한 주 조회가 상한에 닿으면 그 키워드만 하루 단위로 다시 세어 합친다(최대 700건).
# 키워드를 바꾸지 않으므로 과거 기간과 비교가 끊기지 않는다.
RESULT_LIMIT = 100
FETCH_ATTEMPTS = 3
FETCH_BACKOFF_SEC = [5, 15]

# SPEC §2.2 4번(제목 유사도 90%+)은 "구현 부담되면 생략 가능"이라고 돼 있지만
# stdlib difflib라 새 의존성 없이 가능해서 포함함.
TITLE_SIMILARITY_THRESHOLD = 0.90


def normalize_url(url: str) -> str:
    """쿼리스트링(트래킹 파라미터) 제거."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def hash_url(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:16]


def normalize_title(title: str) -> str:
    """특수문자를 공백으로 치환(삭제 아님 - "AI-powered"가 "aipowered"로
    붙어버리면 다른 매체의 "AI powered"와 안 맞아 중복 탐지가 깨진다),
    공백 정리, 소문자화."""
    t = title.lower()
    t = re.sub(r"[^a-z0-9가-힣]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _search_google_news(keyword: str, after: date, before: date, *,
                         hl: str, gl: str, ceid: str, limit: int = RESULT_LIMIT) -> list[dict]:
    """단일 키워드로 Google News RSS 검색, after~before 날짜 범위로 제한한다
    (before는 배타적 - Google 검색 연산자 규칙).
    반환 필드: title, url, published_at('YYYY-MM-DD' 또는 ''), source."""
    query = f"{keyword} after:{after.isoformat()} before:{before.isoformat()}"
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl={hl}&gl={gl}&ceid={ceid}"
    # 예전에는 실패하면 조용히 빈 목록을 돌려줬다. 그러면 "기사 0건"과 "조회 실패"가
    # 구별되지 않아, 일시적 오류가 그 주의 기사 수를 0으로 기록해버린다(백필에서는 그 값이
    # 기준선에 그대로 남는다). 이제 재시도하고, 끝내 실패하면 예외를 올려 호출부가 표시하게 한다.
    root = None
    last_err: Exception | None = None
    for attempt in range(FETCH_ATTEMPTS):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            break
        except Exception as e:  # noqa: BLE001 - 네트워크·파싱 실패를 같이 다룬다
            last_err = e
            if attempt < len(FETCH_BACKOFF_SEC):
                time.sleep(FETCH_BACKOFF_SEC[attempt])
    if root is None:
        raise RuntimeError(f"뉴스 조회 실패({keyword} {after}~{before}): {type(last_err).__name__}")

    results = []
    for item in root.iter("item"):
        if len(results) >= limit:
            break
        title_el = item.find("title")
        link_el = item.find("link")
        if title_el is None or link_el is None or not link_el.text:
            continue
        pub_el = item.find("pubDate")
        published_at = ""
        if pub_el is not None and pub_el.text:
            try:
                published_at = parsedate_to_datetime(pub_el.text).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass
        source_el = item.find("source")
        results.append({
            "title": title_el.text or "",
            "url": link_el.text,
            "published_at": published_at,
            "source": source_el.text if source_el is not None else "",
        })
    return results


def search_google_news_en(keyword: str, after: date, before: date, limit: int = RESULT_LIMIT) -> list[dict]:
    return _search_google_news(keyword, after, before, hl="en-US", gl="US", ceid="US:en", limit=limit)


def search_google_news_kr(keyword: str, after: date, before: date, limit: int = RESULT_LIMIT) -> list[dict]:
    return _search_google_news(keyword, after, before, hl="ko", gl="KR", ceid="KR:ko", limit=limit)


# ── 네이버 뉴스 검색 API (한국 대체 소스) ──────────────────────────────────
#
# 2026-09-28 구글 뉴스 RSS가 GitHub Actions 공유 IP를 막아 전 테마가 0건이 됐다
# (로컬 한국 IP에서는 같은 쿼리가 정상 응답 - 즉 코드가 아니라 IP 문제).
# 야후·pykrx가 같은 이유로 막힌 전례가 있어(마스터플랜 Phase 0), 공식 API로
# 옮기는 쪽이 재발 위험이 낮다.
#
# 구글과 다른 점 두 가지를 알고 써야 한다.
#   1. **날짜 범위 검색이 없다.** `sort=date`로 최신순 정렬해 받아오면서 호출부가
#      원하는 주에 드는 기사만 직접 걸러낸다. 그래서 오래된 주를 백필할수록
#      깊이 페이지를 넘겨야 하고, start 상한(1000)에 걸리면 그 주는 실제보다
#      적게 세어진다.
#   2. **절대 건수가 구글과 다르다.** 뉴스 축은 "직전 8주 중앙값 대비 몇 배"라
#      상대 지표지만, 소스를 바꾸면 기준선이 새 소스 기준으로 8주 쌓일 때까지
#      비율을 믿으면 안 된다.
#
# 2026-10-04 수정: 처음에는 구글처럼 키워드당 100건에서 멈추고 상한에 닿으면 하루씩
# 나눠 다시 셌다. 그런데 네이버는 날짜 검색이 없어서 하루씩 나눠도 매번 최신 기사부터
# 다시 넘겨야 하고, start 상한(1000)에 막혀 앞쪽 날짜에 닿지 못한다. 그 결과 기사가
# 많은 키워드일수록 오히려 적게 세어졌다(하루 300건 키워드가 주 313건, 500건이면 200건 -
# 실제 신호와 반대 방향). 그래서 네이버는 하루 단위로 나누지 않고, 최신순으로 넘길 수
# 있는 데까지(최대 약 1000건) 한 번에 받아 창 안의 기사를 센다. 창 시작일까지 닿지
# 못하면 truncated로 표시해 상한(saturated)으로 기록한다 - 이 경우에도 건수는 실제보다
# 작을 뿐 기사가 많을수록 작아지지는 않는다.
NAVER_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
NAVER_DISPLAY = 100      # 한 번에 받을 수 있는 최대
NAVER_MAX_START = 1000   # start 파라미터 상한 (API 제약)
NAVER_RESULT_LIMIT = NAVER_MAX_START + NAVER_DISPLAY  # 넘길 수 있는 데까지 전부


class NewsResults(list):
    """기사 목록 + 끝까지 못 읽었는지(truncated). 네이버 경로만 truncated를 채운다."""
    truncated: bool = False
_TAG_RE = re.compile(r"<[^>]+>")


def naver_credentials() -> tuple[str, str] | None:
    """(client_id, client_secret) 또는 None. 값은 절대 로그에 찍지 않는다."""
    cid = os.environ.get("NAVER_CLIENT_ID", "").strip()
    secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    return (cid, secret) if cid and secret else None


def _clean_naver_title(raw: str) -> str:
    """네이버는 검색어를 <b>로 감싸 돌려주고 HTML 엔티티도 섞여 온다."""
    text = _TAG_RE.sub("", raw or "")
    for entity, ch in (("&quot;", '"'), ("&amp;", "&"), ("&lt;", "<"),
                       ("&gt;", ">"), ("&apos;", "'"), ("&#39;", "'")):
        text = text.replace(entity, ch)
    return text.strip()


def search_naver_news_kr(keyword: str, after: date, before: date,
                          limit: int = NAVER_RESULT_LIMIT) -> NewsResults:
    """네이버 뉴스 검색 API로 after~before(before 배타적) 기사를 모은다.

    반환 필드는 구글 경로와 동일하다: title, url, published_at, source.
    source는 네이버가 매체명을 따로 주지 않아 원문 링크의 도메인을 쓴다.
    after까지 닿기 전에 start 상한이나 limit에 막히면 반환값의 truncated가 True다.
    """
    creds = naver_credentials()
    if creds is None:
        raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 미설정")
    client_id, client_secret = creds
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}

    results = NewsResults()
    reached_after = False
    start = 1
    while start <= NAVER_MAX_START and len(results) < limit:
        params = {"query": keyword, "display": NAVER_DISPLAY, "start": start, "sort": "date"}
        last_err: Exception | None = None
        payload = None
        for attempt in range(FETCH_ATTEMPTS):
            try:
                resp = requests.get(NAVER_ENDPOINT, params=params, headers=headers, timeout=15)
                resp.raise_for_status()
                payload = resp.json()
                break
            except Exception as e:  # noqa: BLE001 - 네트워크·파싱 실패를 같이 다룬다
                last_err = e
                if attempt < len(FETCH_BACKOFF_SEC):
                    time.sleep(FETCH_BACKOFF_SEC[attempt])
        if payload is None:
            # 구글 경로와 같은 규칙 - 조회 실패를 0건으로 둔갑시키지 않는다.
            raise RuntimeError(
                f"네이버 뉴스 조회 실패({keyword} {after}~{before}): {type(last_err).__name__}")

        items = payload.get("items") or []
        if not items:
            reached_after = True   # 검색 결과 끝 - 더 오래된 기사가 없다
            break

        older_than_window = False
        for item in items:
            pub_raw = item.get("pubDate") or ""
            try:
                published = parsedate_to_datetime(pub_raw).date()
            except (ValueError, TypeError):
                continue  # 날짜를 못 읽으면 어느 주에 넣을지 알 수 없다 - 버린다
            if published >= before:
                continue          # 아직 창보다 최신 - 더 넘겨야 한다
            if published < after:
                older_than_window = True
                break             # 최신순이라 여기부터는 전부 창 밖이다
            url = item.get("originallink") or item.get("link") or ""
            if not url:
                continue
            results.append({
                "title": _clean_naver_title(item.get("title", "")),
                "url": url,
                "published_at": published.isoformat(),
                "source": urlparse(url).netloc,
            })
            if len(results) >= limit:
                break

        if older_than_window or len(items) < NAVER_DISPLAY:
            reached_after = True
            break
        start += NAVER_DISPLAY
        time.sleep(0.2)   # 네이버 요율제한 여유

    results.truncated = not reached_after
    return results


def _collect_by_day(search_fn, keyword: str, after: date, before: date
                     ) -> tuple[list[dict], list[str], list[str]]:
    """상한에 걸린 키워드를 하루씩 나눠 다시 센다. (기사, 상한에 또 닿은 날, 실패한 날)."""
    articles: list[dict] = []
    saturated_days: list[str] = []
    failed_days: list[str] = []
    day = after
    while day < before:
        try:
            got = search_fn(keyword, day, day + timedelta(days=1))
        except Exception as e:  # noqa: BLE001
            failed_days.append(f"{keyword}@{day.isoformat()}: {type(e).__name__}")
            day += timedelta(days=1)
            time.sleep(KEYWORD_SLEEP_SEC)
            continue
        if len(got) >= RESULT_LIMIT:
            saturated_days.append(day.isoformat())
        articles.extend(got)
        day += timedelta(days=1)
        time.sleep(KEYWORD_SLEEP_SEC)
    return articles, saturated_days, failed_days


def dedupe_articles(raw: list[dict]) -> tuple[list[dict], list[dict]]:
    """URL 해시 중복 제거 -> 제목 정규화·유사도(90%+) 중복 제거. 반환: (URL 중복만 뺀 목록, 최종 목록).
    각 항목에 '_url_hash'를 붙인다. 한국 하루 세 번 수집(collect_kr_news_intraday.py)도 같은 규칙을 쓴다."""
    seen_hashes: set[str] = set()
    by_url: list[dict] = []
    for a in raw:
        h = hash_url(a["url"])
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        a["_url_hash"] = h
        by_url.append(a)

    deduped: list[dict] = []
    seen_norm_titles: list[str] = []
    for a in by_url:
        norm = normalize_title(a["title"])
        is_dup = norm in seen_norm_titles or any(
            _title_similarity(norm, s) >= TITLE_SIMILARITY_THRESHOLD for s in seen_norm_titles
        )
        if is_dup:
            continue
        seen_norm_titles.append(norm)
        deduped.append(a)
    return by_url, deduped


def collect_theme_news(keywords: list[str], after: date, before: date, market: str = "US",
                        expand_saturated: bool = True) -> tuple[list[dict], dict]:
    """키워드별로 따로 검색 -> 합치기 -> URL 해시 중복 제거 -> 제목 정규화/유사도
    중복 제거. 반환: (중복 제거된 기사 목록 - 각 항목에 '_url_hash' 추가됨, 통계 dict).

    expand_saturated: 한 키워드가 상한(100건)에 닿으면 그 기간을 하루씩 나눠 다시 세어
    합친다. 상한 때문에 인기 테마의 기사 수가 눌리는 것을 막는다. 하루로 나눠도 상한에
    닿는 키워드는 stats['saturated_keywords']에 남는다 - 그 주의 수치는 실제보다 작다는
    뜻이므로, 쓰는 쪽에서 데이터부족으로 다룰지 판단한다.
    """
    # 한국은 네이버 키가 있으면 네이버를 쓴다(구글 RSS가 Actions IP에서 막힌 뒤의
    # 대체 경로). 키가 없으면 기존 구글 경로 그대로 - 키를 넣고 빼는 것만으로
    # 소스를 되돌릴 수 있게 해서, 새 소스가 이상하면 즉시 원복할 수 있다.
    if market == "KR":
        search_fn = search_naver_news_kr if naver_credentials() else search_google_news_kr
    else:
        search_fn = search_google_news_en
    # 네이버는 하루씩 나눠 다시 세면 오히려 줄어든다(위 네이버 설명 참고) - 한 번에 받는다.
    split_by_day = expand_saturated and search_fn is not search_naver_news_kr
    raw: list[dict] = []
    per_keyword_counts: dict[str, int] = {}
    saturated: list[str] = []
    expanded: list[str] = []
    failed: list[str] = []

    for kw in keywords:
        try:
            articles = search_fn(kw, after, before)
        except Exception as e:  # noqa: BLE001 - 조회 실패는 0건과 구별해서 기록한다
            failed.append(f"{kw}: {type(e).__name__}")
            per_keyword_counts[kw] = 0
            time.sleep(KEYWORD_SLEEP_SEC)
            continue

        if getattr(articles, "truncated", False):
            saturated.append(kw)
        elif split_by_day and len(articles) >= RESULT_LIMIT and (before - after).days > 1:
            day_articles, day_saturated, day_failed = _collect_by_day(search_fn, kw, after, before)
            if day_failed:
                failed.extend(day_failed)
            # 하루 단위 합이 더 적게 나오는 경우(조회 실패 등)는 원래 결과를 쓴다.
            if len(day_articles) >= len(articles):
                articles = day_articles
                expanded.append(kw)
            if day_saturated:
                saturated.append(kw)
        elif search_fn is not search_naver_news_kr and len(articles) >= RESULT_LIMIT:
            saturated.append(kw)

        per_keyword_counts[kw] = len(articles)
        raw.extend(articles)
        time.sleep(KEYWORD_SLEEP_SEC)

    by_url, deduped = dedupe_articles(raw)

    stats = {
        "per_keyword": per_keyword_counts,
        "raw_total": len(raw),
        "after_url_dedup": len(by_url),
        "after_title_dedup": len(deduped),
        "saturated_keywords": saturated,   # 하루로 나눠도 상한 - 실제보다 적게 세어진 키워드
        "expanded_keywords": expanded,     # 상한에 걸려 하루 단위로 다시 센 키워드
        "failed_keywords": failed,         # 조회 자체가 실패한 키워드(0건과 구별)
    }
    return deduped, stats


# ── 미국: Finnhub 기업 뉴스 (소속 기업 뉴스 건수) ─────────────────────────────
#
# 2026-10-04 사용자 결정. 구글 뉴스 RSS가 2026-09-28부터 Actions IP를 막았고, GDELT는 Actions의
# 공유 IP 요율 제한(10회 중 6회 실패)과 수집 공백(2026-09-14 주 전 테마 5% 수준)으로 쓸 수 없었다.
# 그래서 미국 뉴스 축은 **키워드 기사 수가 아니라 "테마 소속 기업들의 기업 뉴스 건수"**로 잰다
# (같은 기사가 여러 소속 기업에 걸리면 한 번만 센다). 한국(키워드 기사 수)과 정의가 다르다 -
# 두 시장의 비율을 서로 비교하지 않는다. SPEC_phase_a_signals.md 2.5.
#
# 실측(2026-10-04, 8주 조회): 27회 호출 실패 0, 36초. 한 응답이 약 250건에서 잘려(BA 240, GE 246)
# 주 단위로만 조회한다 - 대형주도 한 주에 30-60건이라 상한에 닿지 않는다. 닿으면 saturated로 표시.
FINNHUB_ENDPOINT = "https://finnhub.io/api/v1/company-news"
FINNHUB_SLEEP_SEC = 1.1        # 무료 등급 분당 60회
FINNHUB_CAP = 240              # 한 응답이 이 이상이면 잘렸을 수 있다(실측 최대 246)


def finnhub_key() -> str | None:
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    return key or None


def _finnhub_symbol(ticker: str) -> str:
    """클래스 주식 표기(MOG-A)를 Finnhub 표기(MOG.A)로. 실측에서 MOG-A는 0건이었다."""
    return ticker.replace("-", ".")


def _article_key(a: dict) -> str:
    """기사 식별 해시. Finnhub URL은 https://finnhub.io/api/news?id=... 꼴이라 hash_url(쿼리 제거)로는
    모든 기사가 같아진다(2026-10-04 첫 실행에서 테마마다 '중복제거후 1건') - Finnhub 기사 id로 센다."""
    if a.get("id"):
        return hashlib.sha256(f"finnhub:{a['id']}".encode()).hexdigest()[:16]
    return hashlib.sha256(a["url"].encode("utf-8")).hexdigest()[:16]


def fetch_finnhub_company_news(ticker: str, after: date, before: date) -> list[dict]:
    """after~before(before 배타적) 기업 뉴스. 조회 실패는 예외 - 0건으로 둔갑시키지 않는다.

    한 응답이 FINNHUB_CAP 근처면 잘렸을 수 있어 하루씩 나눠 다시 받는다. 대형주(NVDA·TSLA)는
    한 주 조회도 245건 안팎에서 멈췄다(2026-10-04). Finnhub는 날짜 범위 검색이 되므로 나누면 실제로 늘어난다
    (네이버와 다르다). 하루로 나눠도 상한이면 그 결과에 _saturated 표시를 남긴다."""
    items = _fetch_finnhub_range(ticker, after, before)
    if len(items) < FINNHUB_CAP or (before - after).days <= 1:
        return items
    merged: dict[str, dict] = {}
    day = after
    while day < before:
        part = _fetch_finnhub_range(ticker, day, day + timedelta(days=1))
        if len(part) >= FINNHUB_CAP:
            for a in part:
                a["_saturated"] = True
        for a in part:
            merged[_article_key(a)] = a
        day += timedelta(days=1)
        time.sleep(FINNHUB_SLEEP_SEC)
    out = list(merged.values())
    return out if len(out) >= len(items) else items


def _fetch_finnhub_range(ticker: str, after: date, before: date) -> list[dict]:
    from datetime import datetime, timezone
    key = finnhub_key()
    if not key:
        raise RuntimeError("FINNHUB_API_KEY 미설정")
    params = {"symbol": _finnhub_symbol(ticker), "from": after.isoformat(),
              "to": (before - timedelta(days=1)).isoformat(), "token": key}
    last_err: Exception | None = None
    for attempt in range(FETCH_ATTEMPTS):
        try:
            resp = requests.get(FINNHUB_ENDPOINT, params=params, timeout=30)
            if resp.status_code == 429:
                raise RuntimeError("HTTP 429")
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < len(FETCH_BACKOFF_SEC):
                time.sleep(FETCH_BACKOFF_SEC[attempt])
    else:
        raise RuntimeError(f"Finnhub 조회 실패({ticker} {after}~{before}): {type(last_err).__name__}")
    out = []
    for it in data if isinstance(data, list) else []:
        url = it.get("url") or ""
        ts = it.get("datetime")
        if not url or not ts:
            continue
        d = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
        if not (after <= d < before):
            continue
        out.append({"id": it.get("id"), "title": it.get("headline", ""), "url": url,
                    "published_at": d.isoformat(), "source": it.get("source", "")})
    return out


def collect_member_news(members_by_theme: dict[str, list[str]], after: date, before: date
                        ) -> dict[str, tuple[list[dict], dict]]:
    """테마별 소속 기업 뉴스를 모아 기사 단위로 중복 제거한다.

    여러 테마에 같은 종목이 있으면 한 번만 조회한다. 반환: {theme_id: (기사 목록, 통계)}.
    통계의 failed_members가 비어 있지 않으면 그 테마 건수는 불완전하다(쓰는 쪽이 NULL 처리)."""
    cache: dict[str, list[dict] | Exception] = {}
    for tickers in members_by_theme.values():
        for t in tickers:
            if t in cache:
                continue
            try:
                cache[t] = fetch_finnhub_company_news(t, after, before)
            except Exception as e:  # noqa: BLE001
                cache[t] = e
            time.sleep(FINNHUB_SLEEP_SEC)

    result = {}
    for tid, tickers in members_by_theme.items():
        seen: set[str] = set()
        articles: list[dict] = []
        per_member, failed, saturated = {}, [], []
        for t in tickers:
            got = cache[t]
            if isinstance(got, Exception):
                failed.append(f"{t}: {type(got).__name__}")
                continue
            per_member[t] = len(got)
            if any(a.get("_saturated") for a in got):
                saturated.append(t)
            for a in got:
                h = _article_key(a)
                if h in seen:
                    continue
                seen.add(h)
                articles.append({k: v for k, v in a.items() if k != "_saturated"} | {"_url_hash": h})
        result[tid] = (articles, {"per_member": per_member, "raw_total": sum(per_member.values()),
                                  "after_dedup": len(articles), "failed_members": failed,
                                  "saturated_members": saturated, "members": len(tickers)})
    return result
