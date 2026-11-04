"""Phase A-3/B-1: 테마별 뉴스 수집 + 뉴스 축 신호 계산.

SPEC: docs/radar/SPEC_phase_a_signals.md §2
Phase A는 미국 시장만 대상이었으나, Phase B에서 한국(keywords_ko)도 같은
로직으로 처리한다 - 시장별로 그 시장에 해당하는 테마만 순회한다
(themes.yaml의 markets 필드 기준).

weeks-back 하나로 평시 주간 실행과 콜드스타트 백필을 겸한다 - 매주 도는
정상 실행(weeks-back=1)과 최초 8주 백필(weeks-back=8)이 로직상 동일하고
(둘 다 after:/before: 날짜 범위로 특정 주를 조회), 오래된 주부터 최신 주
순서로 처리해야 baseline(직전 8주 중앙값)이 순서대로 쌓이기 때문이다.

Usage:
  python scripts/collect_theme_news.py                        # 이번 주(가장 최근 주)만
  python scripts/collect_theme_news.py --weeks-back 8          # 콜드스타트 백필
  python scripts/collect_theme_news.py --theme-id nuclear_smr  # 특정 테마만
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.db.data_store import get_db
from src.db.theme_signals import (ensure_schema, signal_week_monday, insert_theme_news_bulk, get_prior_news_counts,
                                  upsert_news_signal, news_history_since, get_approved_theme_members,
                                  news_arrow_from_ratio, apply_market_relative_news, NEWS_MARKET_RELATIVE)
from collectors.theme_news_collector import collect_theme_news, collect_member_news, finnhub_key

THEMES_YAML = ROOT / "config" / "themes.yaml"


def _log(msg: str) -> None:
    print(f"[news] {msg}")


def send_telegram_warning(text: str) -> None:
    """수집이 통째로 실패했을 때만 부른다. 미설정이면 조용히 건너뛴다
    (run_watchlist_screen.py의 같은 이름 함수와 동일 패턴)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        _log("TELEGRAM_BOT_TOKEN/CHAT_ID 미설정 - 경고 발송 건너뜀")
        return
    body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        _log("텔레그램 경고 발송 완료")
    except Exception as e:
        _log(f"텔레그램 경고 발송 실패(무시): {type(e).__name__}")


def is_collection_failure(counts: list[int]) -> bool:
    """그 주에 수집한 모든 테마가 0건이면 '뉴스 가뭄'이 아니라 수집 실패로 본다.

    2026-09-28에 구글 뉴스가 Actions IP를 막아 전 테마가 0건이 됐는데, 0이
    그대로 저장되는 바람에 기준선(직전 8주 중앙값)에 0이 섞이기 시작했다.
    0은 NULL이 아니라서 get_prior_news_counts()의 필터에 걸리지 않는다 -
    0이 5주쯤 쌓이면 중앙값이 0이 되고 뉴스 축이 영구히 죽는다.

    테마 하나가 0건인 건 실제 정보다(그 주에 뉴스가 없었다). 하지만 30개
    테마가 **전부** 동시에 0건일 확률은 사실상 없다 - 그건 소스가 막힌 것이다.
    """
    return bool(counts) and all(c == 0 for c in counts)


def member_news_count(articles: list[dict], stats: dict) -> int | None:
    """미국(Finnhub 소속 기업 뉴스) 주간 건수. 소속 중 하나라도 조회에 실패했으면 None.

    일부만 빠진 건수를 저장하면 기준선 대비 가짜 '감소'가 된다 - 계산 불가는 데이터부족이다(원칙 4)."""
    return None if stats.get("failed_members") else len(articles)


BASELINE_WEEKS = 8      # 기준선을 만들 때 참고하는 직전 주 수
BASELINE_MIN_WEEKS = 4  # 이만큼도 없으면 판정 보류


def compute_news_arrow(news_count: int, min_articles: int, prior_counts: list[int],
                        thresholds: dict) -> tuple[float | None, float | None, str]:
    """SPEC §2.3 판정 로직. 반환: (baseline, ratio, arrow).

    기준선은 직전 8주의 **중앙값**이다(2026-09-16 변경, 이전에는 직전 4주 평균).
    평균 4주는 한 주 급증이 그다음 4주의 기준선을 통째로 끌어올려, 테마가 실제로
    달아오르는 구간에서 오히려 화살표가 죽는 문제가 있었다. 중앙값은 그 급증 주를
    한 표로만 세고, 8주로 넓히면 기준선 자체가 덜 출렁인다.
    """
    if len(prior_counts) < BASELINE_MIN_WEEKS:
        return None, None, "na"
    baseline = statistics.median(prior_counts)
    if news_count < min_articles or baseline == 0:
        return baseline, None, "na"
    ratio = news_count / baseline
    return baseline, ratio, news_arrow_from_ratio(ratio, thresholds)


def load_active_themes(theme_ids: list[str] | None) -> tuple[list[dict], dict]:
    with open(THEMES_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    themes = [t for t in data["themes"] if t.get("status") == "active"]
    if theme_ids:
        wanted = set(theme_ids)
        themes = [t for t in themes if t["id"] in wanted]
    return themes, data.get("config", {})


def _report_market_relative(conn, market: str, week: str, thresholds: dict) -> None:
    if market not in NEWS_MARKET_RELATIVE:
        return
    median, n = apply_market_relative_news(conn, market, week, thresholds)
    if median is None:
        _log(f"{market} {week}: 비율 있는 테마가 모자라 시장 대비 판정 안 함(자기 기준선 대비 그대로)")
    else:
        _log(f"{market} {week}: 뉴스 시장 대비 판정 - 테마 비율 중앙값 {median:.2f}배, {n}개 테마")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weeks-back", type=int, default=1,
                         help="처리할 주 수 (1=이번 주만, 8=콜드스타트 백필)")
    parser.add_argument("--theme-id", nargs="*", default=None, help="특정 테마만 (비우면 전체)")
    parser.add_argument("--market", choices=["US", "KR"], default=None,
                         help="한 시장만 (비우면 둘 다). 한쪽만 다시 돌릴 때 쓴다 - 둘 다 돌리면 "
                              "Actions에서 70-90분이 걸린다")
    parser.add_argument("--recalc-relative", metavar="WEEK", default=None,
                         help="수집 없이 그 주(월요일 YYYY-MM-DD)의 뉴스 화살표만 시장 대비로 다시 판정한다")
    args = parser.parse_args()

    if args.recalc_relative:
        _, config = load_active_themes(None)
        conn = get_db()
        ensure_schema(conn)
        for mk in sorted(NEWS_MARKET_RELATIVE):
            _report_market_relative(conn, mk, args.recalc_relative,
                                    config.get("news_thresholds", {"strong_up": 2.0, "up": 1.3, "down": 0.7}))
        conn.close()
        return

    themes, config = load_active_themes(args.theme_id)
    if not themes:
        _log("대상 테마 없음")
        sys.exit(1)
    default_min_articles = config.get("default_min_articles", 10)
    thresholds = config.get("news_thresholds", {"strong_up": 2.0, "up": 1.3, "down": 0.7})

    conn = get_db()
    ensure_schema(conn)

    current_week = signal_week_monday(date.today())
    weeks = [current_week - timedelta(weeks=i) for i in range(args.weeks_back - 1, -1, -1)]

    KEYWORD_FIELD = {"US": "keywords_en", "KR": "keywords_ko"}

    failed_runs: list[str] = []

    for market, keyword_field in KEYWORD_FIELD.items():
        if args.market and market != args.market:
            continue
        market_themes = [t for t in themes if market in t.get("markets", [])]
        # 미국은 Finnhub 키가 있으면 소속 기업 뉴스 건수로 잰다(2026-10-04, theme_news_collector 설명).
        # 소속은 다른 축과 같은 direct+partial - perceived(시장 인식)는 넣지 않는다.
        member_mode = market == "US" and finnhub_key() is not None
        members_by_theme: dict[str, list[str]] = {}
        collectible = []
        for theme in market_themes:
            if member_mode:
                tickers = [m["ticker"] for m in get_approved_theme_members(conn, theme["id"], market)]
                if tickers:
                    members_by_theme[theme["id"]] = tickers
                    collectible.append(theme)
                else:
                    _log(f"{theme['id']}({market}): 승인된 소속 없음 - 건너뜀")
            elif theme.get(keyword_field):
                collectible.append(theme)
            else:
                _log(f"{theme['id']}({market}): {keyword_field} 없음 - 건너뜀")
        if member_mode:
            _log(f"{market}: Finnhub 소속 기업 뉴스 모드, 종목 "
                 f"{len({t for v in members_by_theme.values() for t in v})}개")
        _log(f"대상 테마 {len(collectible)}개({market}), 처리 주 {len(weeks)}개 "
             f"({weeks[0].isoformat()} ~ {weeks[-1].isoformat()})")

        # 주를 바깥 루프로 둔다 - 그 주의 모든 테마를 먼저 받아봐야 "전 테마 0건"
        # (= 수집 실패)인지 알 수 있고, 그걸 알아야 0을 저장할지 NULL을 저장할지
        # 정할 수 있다. 기준선은 각 테마의 **이전 주** 값만 쓰므로 주를 오름차순으로
        # 도는 한 이 순서 변경이 계산에 주는 영향은 없다.
        for week_start in weeks:
            week_end = week_start + timedelta(days=7)  # before: 는 배타적이라 +7로 일요일까지 포함
            backfilled = week_start != current_week

            fetched = []
            member_results = (collect_member_news(members_by_theme, week_start, week_end)
                              if member_mode else {})
            for theme in collectible:
                theme_id = theme["id"]
                if member_mode:
                    articles, stats = member_results[theme_id]
                    insert_theme_news_bulk(conn, theme_id, market, week_start.isoformat(), articles)
                    _log(f"{theme_id}({market}) {week_start.isoformat()}: 소속 {stats['members']}종목 "
                         f"원본 {stats['raw_total']}건 -> 중복제거후 {len(articles)}건 "
                         f"(종목별 {stats['per_member']}"
                         f"{', 조회실패 ' + str(stats['failed_members']) if stats['failed_members'] else ''}"
                         f"{', 상한 ' + str(stats['saturated_members']) if stats['saturated_members'] else ''})")
                    # 소속 중 하나라도 조회에 실패하면 그 주 건수는 실제보다 작게 세어진 것이라 비율이
                    # 가짜 '감소'로 나온다 - 원칙 4(계산 불가는 데이터부족)대로 None -> NULL 저장.
                    count = member_news_count(articles, stats)
                    fetched.append((theme, count))
                    continue
                articles, stats = collect_theme_news(
                    theme[keyword_field], week_start, week_end, market=market)
                insert_theme_news_bulk(conn, theme_id, market, week_start.isoformat(), articles)
                _log(f"{theme_id}({market}) {week_start.isoformat()}: 원본 {stats['raw_total']}건 -> "
                     f"URL중복제거후 {stats['after_url_dedup']}건 -> 제목중복제거후 {len(articles)}건 "
                     f"(키워드별 {stats['per_keyword']})")
                fetched.append((theme, len(articles)))

            collection_failed = is_collection_failure([c or 0 for _, c in fetched])
            if collection_failed:
                msg = (f"{market} {week_start.isoformat()}: 테마 {len(fetched)}개가 전부 0건 - "
                       f"수집 실패로 보고 건수를 NULL로 저장한다(0으로 저장하면 기준선이 오염된다)")
                _log(f"  ** 경고 ** {msg}")
                failed_runs.append(f"{'미국' if market == 'US' else '한국'} {week_start.month}/{week_start.day} 주 "
                                   f"- 테마 {len(fetched)}개 모두 기사 0건")

            for theme, article_count in fetched:
                theme_id = theme["id"]
                min_articles = theme.get("min_articles", default_min_articles)
                # 키워드가 바뀐 테마는 바뀐 주 이전 건수를 기준선에 쓰지 않는다(유지보수 규칙 2).
                # 기준선 최소 4주가 쌓일 때까지 뉴스 축은 na(데이터부족)로 남는다 - 탈락이 아니다.
                # 수집원이 바뀐 시장도 같다(KR: 구글 -> 네이버, theme_signals.NEWS_SOURCE_SWITCH_WEEK).
                since = news_history_since(theme, market)

                prior_counts = get_prior_news_counts(conn, theme_id, market, week_start.isoformat(),
                                                     weeks=BASELINE_WEEKS, since=since)
                if collection_failed or article_count is None:
                    # 건수를 모르는 것이지 0인 게 아니다 - NULL로 남겨 기준선 계산에서 빠지게 한다.
                    news_count = None
                    baseline, ratio, arrow = None, None, "na"
                else:
                    news_count = article_count
                    baseline, ratio, arrow = compute_news_arrow(
                        news_count, min_articles, prior_counts, thresholds)

                ratio_str = f"{ratio:.2f}" if ratio is not None else "-"
                baseline_str = f"{baseline:.1f}" if baseline is not None else "-"
                _log(f"  -> {theme_id} baseline={baseline_str} ratio={ratio_str} arrow={arrow} "
                     f"(count={'NULL(수집실패)' if news_count is None else news_count}, "
                     f"backfilled={backfilled}, 직전주 {len(prior_counts)}개 확보"
                     f"{', 키워드·수집원 변경 ' + since + ' 이후만' if since else ''})")

                upsert_news_signal(
                    conn, theme_id, market, week_start.isoformat(), news_count, baseline,
                    ratio, arrow, backfilled, datetime.utcnow().isoformat(),
                )
            conn.commit()
            # 미국은 위에서 낸 자기 기준선 대비 화살표를 시장 전체 대비로 다시 판정한다(실적 철 동반 상승 제거).
            _report_market_relative(conn, market, week_start.isoformat(), thresholds)

    conn.close()
    if failed_runs:
        send_telegram_warning(
            "⚠️ <b>U-Sonar 테마 뉴스 수집 실패</b>\n"
            + "\n".join(f"· {r}" for r in failed_runs)
            + "\n\n뉴스 출처가 막혔거나 연결이 끊긴 것으로 보입니다. "
              "이번 주 뉴스 축은 '데이터 부족'으로 표시되고, 기준선 계산에는 넣지 않습니다."
        )
    _log("완료" + (f" - 수집 실패 {len(failed_runs)}건" if failed_runs else ""))


if __name__ == "__main__":
    main()
