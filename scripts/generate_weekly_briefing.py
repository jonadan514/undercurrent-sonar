"""주간 브리핑 생성 — 주간 워치리스트 스크리닝 직후(일요일 밤) 실행.

한 주의 데이터를 모아 구조화된 브리핑을 만들고:
  1. Turso weekly_briefings 테이블에 저장 (웹 '주간 브리핑' 탭이 읽음)
  2. 텔레그램으로 요약 발송

섹션:
  - 지난주 시장 궤적 (US/KR 지수 주간 등락)
  - 워치리스트 변동 (신규 진입/탈락 — watchlist_weekly_snapshots 비교)
  - 관심도 흐름 (한 주간 sentiment 상승 종목)
  - 이번 주 실적 발표 (워치리스트·내 관심·관찰 노트 종목, earnings_calendar + 한국 결산실적 공시예고 - 2026-10-17)
  - 한국 공시 지난 7일 (공급계약·잠정실적, kr_disclosures - 2026-10-17)
  - GPT 총평 · 다음 주 관전 포인트 (웹에만 - 텔레그램은 DB·시세 숫자만, 2026-10-05)
  - 테마 레이더 라벨 변동 (미국·한국)

Usage: python scripts/generate_weekly_briefing.py [--no-telegram]
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db.turso_http import as_bool, get_credentials, query as _turso_query
from src.analyzers.signal_check import sentiment_window
from src.analyzers.theme_labels import label_display
from src.collectors.kr_disclosures import amount_changed, prelim_has_values, quarter_label, summary as disclosure_summary

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SENTIMENT_RANK = {"COLD": 0, "WARM": 1, "HOT": 2}
SENTIMENT_KO = {"COLD": "낮음", "WARM": "보통", "HOT": "높음"}
SITE_URL = "https://u-sonar.vercel.app"
MARKET_FLAG = {"US": "🇺🇸", "KR": "🇰🇷"}


def _md(day: str | None) -> str:
    """'2026-09-28' -> '9/28'. 텔레그램에서 날짜를 짧게 읽히게."""
    if not day:
        return "-"
    _y, m, d = day.split("-")
    return f"{int(m)}/{int(d)}"
THEMES_YAML = ROOT / "config" / "themes.yaml"


def load_theme_names() -> dict[str, str]:
    """scripts/send_radar_digest.py와 동일한 패턴."""
    with open(THEMES_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {t["id"]: t["name_ko"] for t in data["themes"]}


# ── Turso (Hrana v2 HTTP) — 다른 스크립트와 동일 패턴 ──────────────────────

def _require_turso() -> None:
    if not get_credentials():
        logger.error("TURSO_DATA_URL / TURSO_DATA_TOKEN 미설정")
        sys.exit(1)


def turso_exec(sql: str, args: list | None = None) -> list[dict]:
    _require_turso()
    try:
        return _turso_query(sql, args)
    except Exception as e:
        logger.warning("Turso 실패 (%s): %s", sql[:50], type(e).__name__)
        return []


def _payload(rows: list[dict], key: str = "payload") -> list[dict]:
    out = []
    for r in rows:
        try:
            out.append({**r, "_data": json.loads(r[key])})
        except Exception:
            continue
    return out


# ── 섹션 수집 ────────────────────────────────────────────────────────────────

def get_market_week(market: str) -> dict:
    """지수 주간 등락."""
    idx_chg = None
    try:
        import yfinance as yf
        ticker = "^KS11" if market == "KR" else "SPY"
        hist = yf.Ticker(ticker).history(period="7d", auto_adjust=True)["Close"].dropna()
        if len(hist) >= 2:
            idx_chg = round(float(hist.iloc[-1] / hist.iloc[0] - 1) * 100, 2)
    except Exception:
        pass

    return {"index_chg_1w": idx_chg}


def get_macro_week() -> dict | None:
    """금리·환율 1주 변화 - 매일 도는 macro_snapshot(src/analyzers/macro_snapshot.py)의 최신 행을 그대로 쓴다.
    chg_1w는 5거래일 전 대비 차이(금리는 %p, 환율은 원). 표가 없거나 비면 None - 브리핑은 그 줄만 뺀다."""
    try:
        rows = _payload(turso_exec("SELECT date, payload FROM macro_snapshot ORDER BY date DESC LIMIT 1"))
    except Exception:
        return None
    if not rows:
        return None
    items = rows[0]["_data"].get("items") or {}
    # dxy(달러인덱스)·wti(유가)는 2026-10-09 추가 - 원/달러가 달러 강세 탓인지, 에너지 테마 해석용
    # copper(구리)는 2026-10-17 추가 - 웹 브리핑에만 표시(텔레그램 지표 줄은 늘리지 않는다)
    # natgas·hy_spread·real10y는 2026-10-17 추가 - 웹 브리핑만(텔레그램 지표 줄은 늘리지 않는다)
    # vix·spread_10y_2y는 2026-11-05 추가(BACKLOG A) - 웹 브리핑 칸 + 텔레그램은 VIX만 지수 줄 끝에(지표 줄은 늘리지 않는다)
    pick = {k: items.get(k) for k in ("us10y", "usdkrw", "dxy", "wti", "copper", "natgas", "hy_spread", "real10y",
                                       "vix", "spread_10y_2y")}
    pick["kr3y"] = get_kr_rate_week("kr3y")
    if not any(v and v.get("value") is not None for v in pick.values()):
        return None
    return {"as_of": rows[0]["_data"].get("date") or rows[0].get("date"), **pick}


def _pct_chg(item: dict) -> str:
    """유가처럼 수준보다 변화율이 읽기 쉬운 값 - 저장된 값과 1주 차이로 1주 전 대비 %를 낸다."""
    v, c = item.get("value"), item.get("chg_1w")
    if v is None or c is None or v - c == 0:
        return ""
    return f" ({c / (v - c) * 100:+.1f}%)"


def fmt_krw_flow(v: float | None) -> str:
    """순매수 금액(원) -> '+1.2조' / '-3,204억'. 숫자는 저장값 그대로, 단위만 바꾼다."""
    if v is None:
        return "-"
    if abs(v) >= 1e12:
        return f"{v / 1e12:+.1f}조"
    return f"{v / 1e8:+,.0f}억"


def sum_flows(rows: list[dict], days: int = 5) -> dict | None:
    """kr_investor_flows 행들 -> 시장별 최근 days 거래일 투자자별 합계. 거래일은 시장마다 그 시장 날짜로 센다."""
    by_market: dict[str, dict[str, dict[str, float]]] = {}
    for r in rows:
        by_market.setdefault(r["market"], {}).setdefault(r["date"], {})[r["investor"]] = float(r["value"])
    out: dict = {}
    for market, by_date in by_market.items():
        dates = sorted(by_date, reverse=True)[:days]
        if not dates:
            continue
        sums: dict[str, float] = {}
        for d in dates:
            for inv, v in by_date[d].items():
                sums[inv] = sums.get(inv, 0.0) + v
        out[market] = {**sums, "days": len(dates), "from": dates[-1], "to": dates[0]}
    return out or None


def get_kr_flows_week() -> dict | None:
    """코스피·코스닥 투자자별 순매수 최근 5거래일 합계(kr_investor_flows, scripts/save_kr_investor_flows.py).
    표가 없거나 비면 None - 브리핑은 그 부분만 뺀다."""
    try:
        rows = turso_exec("SELECT date, market, investor, value FROM kr_investor_flows "
                          "WHERE date >= date('now', '-20 days') ORDER BY date DESC")
    except Exception:
        return None
    return sum_flows(rows)


def get_regime_week() -> dict | None:
    """시장 환경 축(2026-11-07, market_regime_weekly - scripts/compute_market_regime.py가 일요일 브리핑 전에 쌓는다).
    시장마다 가장 최근 주. 기준 금요일이 10일보다 오래됐으면(정기 계산 실패) 빼고, 표가 없으면 None - 브리핑은 그 줄만 뺀다."""
    try:
        rows = turso_exec("SELECT week, market, as_of, payload FROM market_regime_weekly ORDER BY week DESC LIMIT 6")
    except Exception:
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")
    out: dict = {}
    for r in rows:
        if r["market"] in out or str(r["as_of"]) < cutoff:
            continue
        try:
            out[r["market"]] = {"week": r["week"], **json.loads(r["payload"])}
        except Exception:
            continue
    return out or None


def get_kr_rate_week(key: str) -> dict | None:
    """국고채 금리(kr_rates, scripts/save_kr_treasury.py - pykrx) 최신 값과 5거래일 전 대비 차이(%p).
    macro_snapshot의 chg_1w와 같은 '5거래일 전' 기준. 표가 없거나 비면 None."""
    try:
        rows = turso_exec("SELECT date, value FROM kr_rates WHERE key = ? ORDER BY date DESC LIMIT 12", [key])
    except Exception:
        return None
    vals = [float(r["value"]) for r in rows if r.get("value") is not None]
    # 휴장일에 직전 값이 그대로 들어온 행이 섞여 있어도 "5거래일 전"이 밀리지 않게 연속 같은 값은 하나로
    vals = [v for i, v in enumerate(vals) if i == 0 or v != vals[i - 1]]
    if not vals:
        return None
    return {"value": vals[0], "chg_1w": round(vals[0] - vals[5], 4) if len(vals) >= 6 else None,
            "as_of": rows[0]["date"]}


# 전체 미리 보기(--dry-run, 2026-11-05) - 아무것도 쓰지 않는다. 스냅샷 저장까지 건너뛰어야 일요일 실제 실행의 신규·탈락 비교가
# 목요일 미리 보기 목록과 비교되는 일이 없다.
DRY_RUN = [False]


def get_watchlist_changes() -> dict:
    """이번 주 후보 vs 지난주 스냅샷 비교 → 신규/탈락. 이번 주 스냅샷 저장."""
    turso_exec(
        "CREATE TABLE IF NOT EXISTS watchlist_weekly_snapshots ("
        "  week TEXT PRIMARY KEY, payload TEXT NOT NULL,"
        "  created_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )

    current = turso_exec(
        "SELECT market, symbol, name FROM watchlist_candidates ORDER BY market, symbol"
    )
    cur_map = {f"{c['market']}:{c['symbol']}": c for c in current}

    prev_rows = _payload(turso_exec(
        "SELECT week, payload FROM watchlist_weekly_snapshots ORDER BY week DESC LIMIT 1"
    ))
    prev_map: dict[str, dict] = {}
    if prev_rows:
        prev_map = {f"{c['market']}:{c['symbol']}": c for c in prev_rows[0]["_data"]}

    added   = [cur_map[k] for k in cur_map if k not in prev_map]
    removed = [prev_map[k] for k in prev_map if k not in cur_map]

    # 이번 주 스냅샷 저장 (월요일 날짜 기준)
    week = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not DRY_RUN[0]:
        turso_exec(
            "INSERT INTO watchlist_weekly_snapshots (week, payload) VALUES (?, ?) "
            "ON CONFLICT(week) DO UPDATE SET payload=excluded.payload",
            [week, json.dumps(current, ensure_ascii=False)],
        )

    return {
        "total": len(current),
        # 목록은 10개까지만 담고, 건수는 자르기 전 전체를 따로 둔다 - 예전엔 자른 목록 길이를 세서
        # 신규가 30개여도 "신규 10"으로 나왔다(2026-10-05 수정).
        "added": added[:10],
        "removed": removed[:10],
        "added_count": len(added),
        "removed_count": len(removed),
        "has_prev": bool(prev_map),
    }


TURNAROUND_LIST_MAX = 10


def is_turnaround(c: dict) -> bool:
    """워치리스트 '실적 반전'과 같은 조건(frontend/app/watchlist/page.tsx isTurnaround) - 매출 3년 판정은 정체·역성장인데
    지금 흐름은 성장. 지금 흐름 = 최근 4개 분기 합 비교(rev_ttm_tier)가 있으면 그것, 없으면 최근 분기 전년동기(rev_q_tier)."""
    if c.get("growth_tier") not in ("정체", "역성장"):
        return False
    now = c.get("rev_ttm_tier") if c.get("rev_ttm_tier") is not None else c.get("rev_q_tier")
    return now == "성장"


def _turnaround_item(c: dict) -> dict:
    ttm = c.get("rev_ttm_tier") is not None
    return {"market": c["market"], "symbol": c["symbol"], "name": c.get("name"),
            "basis": "1년" if ttm else "분기", "yoy": c.get("rev_ttm_yoy") if ttm else c.get("rev_q_yoy")}


def turnaround_diff(current: list[dict], prev: list[dict] | None) -> dict:
    """이번 주 실적 반전 목록 vs 직전 스냅샷. 순위 없이 시장·종목코드 순(원칙 1)."""
    cur = sorted((_turnaround_item(c) for c in current if is_turnaround(c)), key=lambda x: (x["market"], x["symbol"]))
    by_market: dict[str, int] = {}
    for x in cur:
        by_market[x["market"]] = by_market.get(x["market"], 0) + 1
    out = {"total": len(cur), "by_market": by_market, "has_prev": prev is not None,
           "added": [], "added_count": 0, "removed": [], "removed_count": 0, "items": cur}
    if prev is not None:
        prev_keys = {f"{p['market']}:{p['symbol']}" for p in prev}
        cur_keys = {f"{x['market']}:{x['symbol']}" for x in cur}
        added = [x for x in cur if f"{x['market']}:{x['symbol']}" not in prev_keys]
        removed = [p for p in prev if f"{p['market']}:{p['symbol']}" not in cur_keys]
        out.update(added=added[:TURNAROUND_LIST_MAX], added_count=len(added),
                   removed=removed[:TURNAROUND_LIST_MAX], removed_count=len(removed))
    return out


def get_turnaround_changes(week: str) -> dict | None:
    """워치리스트 '실적 반전' 종목의 주간 변동(2026-10-17). 이번 주 목록은 스냅샷으로 남기고(덮어쓰지 않음, 원칙 5)
    직전 주 스냅샷과 비교한다. 성장 열이 아직 없으면 None - 브리핑은 그 칸만 뺀다."""
    try:
        current = turso_exec(
            "SELECT market, symbol, name, growth_tier, rev_ttm_tier, rev_ttm_yoy, rev_q_tier, rev_q_yoy "
            "FROM watchlist_candidates ORDER BY market, symbol")
    except Exception as e:  # noqa: BLE001
        logger.warning("실적 반전 조회 실패(열 없음?) - 건너뜀: %s", e)
        return None
    turso_exec(
        "CREATE TABLE IF NOT EXISTS turnaround_weekly_snapshots ("
        "  week TEXT PRIMARY KEY, payload TEXT NOT NULL,"
        "  created_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    prev_rows = _payload(turso_exec(
        "SELECT week, payload FROM turnaround_weekly_snapshots WHERE week < ? ORDER BY week DESC LIMIT 1", [week]))
    result = turnaround_diff(current, prev_rows[0]["_data"] if prev_rows else None)
    if not DRY_RUN[0]:
        turso_exec("INSERT OR IGNORE INTO turnaround_weekly_snapshots (week, payload) VALUES (?, ?)",
                   [week, json.dumps(result["items"], ensure_ascii=False)])
    result.pop("items")
    return result


EARNINGS_TG_MAX = 6
EARNINGS_TAG_KO = {"my": "내 관심", "note": "노트", "turnaround": "실적 반전"}


def merge_kr_notices(rows: list[dict], notices: list[dict], since: str) -> list[dict]:
    """한국 결산실적 공시예고(DART, 회사가 정한 날짜)를 yfinance 날짜보다 우선한다. notices: {ticker, announce_date}.
    같은 종목에 예고가 여러 건이면 늦게 낸 것(목록 뒤쪽). since(브리핑 주 월요일)보다 이른 예고 날짜는 쓰지 않는다 -
    이미 지난 잠정실적 예고가 yfinance의 다음 발표일(확정 실적 등)을 덮어 그 주에서 종목이 사라지면 안 된다(10/17 리뷰)."""
    by_key = {(r["market"], r["ticker"]): dict(r) for r in rows}
    for n in notices:
        if not n.get("announce_date") or n["announce_date"] < since:
            continue
        by_key[("KR", n["ticker"])] = {"ticker": n["ticker"], "market": "KR", "earnings_date": n["announce_date"],
                                       "earnings_date_end": n["announce_date"], "is_estimate": 0, "source": "DART"}
    return list(by_key.values())


def earnings_week_items(rows: list[dict], week: str, tags: dict[str, list[str]], names: dict[str, str]) -> dict:
    """이번 주(week 월요일~일요일)에 발표 예정인 종목. 예상 범위는 시작일이 이번 주에 들면 넣는다.
    tags: {"KR:005930": ["my", ...]} - 표시 순서만 정할 뿐 점수가 아니다(원칙 1). 날짜·시장·종목코드 순."""
    mon = datetime.strptime(week, "%Y-%m-%d").date()
    sun = mon + timedelta(days=6)
    items = []
    for r in rows:
        try:
            d = datetime.strptime(str(r["earnings_date"])[:10], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if not (mon <= d <= sun):
            continue
        key = f"{r['market']}:{r['ticker']}"
        items.append({"market": r["market"], "symbol": r["ticker"], "name": names.get(key),
                      "date": d.isoformat(), "date_end": str(r.get("earnings_date_end") or d.isoformat())[:10],
                      "estimate": as_bool(r.get("is_estimate")), "tags": tags.get(key, [])})
    items.sort(key=lambda x: (x["date"], x["market"], x["symbol"]))
    by_market: dict[str, int] = {}
    for x in items:
        by_market[x["market"]] = by_market.get(x["market"], 0) + 1
    return {"total": len(items), "by_market": by_market, "tagged_count": sum(1 for x in items if x["tags"]),
            "items": items}


def kr_name_table() -> dict[str, str]:
    """한국 종목코드 -> 이름(2026-11-11). 유니버스 파일, 그다음 화면이 쓰는 이름표(frontend/src/lib/krStockNames.ts).
    둘 다 없으면 빈 표 - 그 종목은 코드로 나온다."""
    out: dict[str, str] = {}
    try:
        ts = (ROOT / "frontend" / "src" / "lib" / "krStockNames.ts").read_text(encoding="utf-8")
        out.update({f"KR:{c}": n for c, n in re.findall(r'"(\d{6})":\s*"([^"]+)"', ts)})
    except Exception:  # noqa: BLE001
        pass
    try:
        out.update({f"KR:{i['symbol']}": i["name"] for i in json.loads(KR_UNIVERSE.read_text(encoding="utf-8")).get("items", [])
                    if i.get("name")})
    except Exception:  # noqa: BLE001
        pass
    return out


def get_earnings_week(week: str) -> dict | None:
    """이번 주 실적 발표 예정(2026-10-17) - earnings_calendar(scripts/collect_earnings_calendar.py)의 종목별 최근 수집 행.
    2주 넘게 갱신 안 된 행은 쓰지 않는다. 표가 없거나 비면 None - 브리핑은 그 칸만 뺀다."""
    try:
        rows = turso_exec(
            "SELECT e.ticker, e.market, e.earnings_date, e.earnings_date_end, e.is_estimate FROM earnings_calendar e "
            "JOIN (SELECT ticker, market, MAX(fetched_on) AS f FROM earnings_calendar GROUP BY ticker, market) l "
            "ON e.ticker = l.ticker AND e.market = l.market AND e.fetched_on = l.f "
            "WHERE e.fetched_on >= date('now', '-14 days')")
    except Exception as e:  # noqa: BLE001
        logger.warning("실적 발표일 조회 실패(표 없음?) - 건너뜀: %s", e)
        rows = []
    try:
        # 한국 결산실적 공시예고(2026-10-17) - 유니버스 밖 상장사도 관심 종목이면 표시된다(아래 tags 기준으로 거른다)
        notices = [{"ticker": r["stock_code"], "announce_date": json.loads(r["payload"]).get("announce_date")}
                   for r in turso_exec("SELECT stock_code, payload FROM kr_disclosures WHERE kind = 'notice' "
                                       "AND rcept_dt >= date('now', '-60 days') ORDER BY rcept_dt, rcept_no")]
    except Exception:  # noqa: BLE001 - 공시 표가 아직 없으면 yfinance만
        notices = []
    if not rows and not notices:
        return None
    tags: dict[str, list[str]] = {}
    names: dict[str, str] = {}

    def tag(key: str, t: str) -> None:
        if t not in tags.setdefault(key, []):
            tags[key].append(t)

    for sql, kind in (("SELECT market, symbol, name FROM my_watchlist", "my"),
                      ("SELECT DISTINCT market, ticker AS symbol, NULL AS name FROM observations "
                       "WHERE kind = 'stock' AND ticker IS NOT NULL", "note")):
        try:
            for r in turso_exec(sql):
                key = f"{r['market']}:{r['symbol']}"
                tag(key, kind)
                if r.get("name"):
                    names[key] = r["name"]
        except Exception:  # noqa: BLE001 - 표가 없으면 그 표시만 빠진다
            pass
    try:
        cands = turso_exec("SELECT market, symbol, name, growth_tier, rev_ttm_tier, rev_q_tier FROM watchlist_candidates")
    except Exception:  # noqa: BLE001 - 성장 열이 없으면 이름만
        cands = turso_exec("SELECT market, symbol, name FROM watchlist_candidates")
    for c in cands:
        key = f"{c['market']}:{c['symbol']}"
        if c.get("name"):
            names.setdefault(key, c["name"])
        if is_turnaround(c):
            tag(key, "turnaround")
    for k, v in kr_name_table().items():   # 테마 소속 종목(2026-11-08부터 수집)은 위 표에 이름이 없다
        names.setdefault(k, v)
    # 공시예고는 전체 상장사라 워치리스트 후보·내 관심·노트 종목만 남긴다(yfinance 대상과 같은 범위)
    targets = {f"{c['market']}:{c['symbol']}" for c in cands} | set(tags)
    notices = [n for n in notices if f"KR:{n['ticker']}" in targets]
    return earnings_week_items(merge_kr_notices(rows, notices, week), week, tags, names)


KR_UNIVERSE = ROOT / "data" / "kr_universe.json"
US_LISTS = (ROOT / "data" / "sp500_list.csv", ROOT / "data" / "sp400_list.csv")
DISC_TG_MAX = 5
DISC_WEB_MAX = 30
DISC_TAG_KO = {"my": "내 관심", "note": "노트", "cand": "워치", "theme": "테마"}


def kr_disclosures_week(rows: list[dict], universe: set[str], tags: dict[str, list[str]]) -> dict:
    """지난 7일 한국 공시(공급계약·잠정실적) - 유니버스(시총 3000억+) 또는 관심 표시가 붙은 종목만.
    공급계약은 관심 종목 먼저, 그다음 매출 대비 큰 순 - 공시에 적힌 비율 그대로 정렬할 뿐 점수가 아니다(원칙 1).
    잠정실적은 관심 종목 먼저, 그다음 접수일 순."""
    out: dict = {}
    # termination(계약 해지)·amend(계약금액 정정, 금액이 바뀐 것만)은 2026-10-21 추가
    for kind in ("contract", "prelim", "termination", "amend"):
        items = []
        for r in rows:
            if r["kind"] != kind or not (r["stock_code"] in universe or tags.get(r["stock_code"])):
                continue
            p = r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"] or "{}")
            if kind == "prelim" and not prelim_has_values(p):
                continue
            if kind == "amend" and not amount_changed(p):
                continue
            items.append({"symbol": r["stock_code"], "name": r.get("corp_name"), "date": r["rcept_dt"],
                          "rcept_no": r["rcept_no"], "tags": tags.get(r["stock_code"], []), "summary": disclosure_summary(kind, p),
                          **({"amount": p.get("amount"), "pct": p.get("pct_of_revenue"), "title": p.get("title"),
                              "withheld": bool(p.get("withheld")) and p.get("amount") is None} if kind in ("contract", "termination") else
                             {"amount_before": p.get("amount_before"), "amount_after": p.get("amount_after"),
                              "pct_before": p.get("pct_before"), "pct_after": p.get("pct_after"), "title": p.get("title")} if kind == "amend" else
                             {"quarter": quarter_label(p.get("period_end"), p.get("monthly"), p.get("annual")),
                              **{k: p.get(k) for k in ("revenue_yoy_pct", "revenue_yoy_turn", "operating_income_yoy_pct",
                                                       "operating_income_yoy_turn", "revenue", "operating_income")}})})
        if kind in ("contract", "termination"):
            items.sort(key=lambda x: (not x["tags"], -(x["pct"] if x["pct"] is not None else -1), x["date"]))
        else:
            items.sort(key=lambda x: (not x["tags"], x["date"], x["symbol"]))
        out[kind] = {"count": len(items), "items": items[:DISC_WEB_MAX]}
    return out


INSIDER_TG_MAX = 5
INSIDER_DISC_TG_MAX = 5
FIN_KO = {"pass": "재무 통과", "fail": "재무 탈락", "insufficient": "재무 데이터부족"}
INSIDER_WEB_MAX = 30


def fmt_money(v: float | None, market: str) -> str:
    """미국 달러 -> '$250K' / '$1.2M', 한국 원 -> '2.5억' / '1.2조'."""
    if v is None:
        return "-"
    if market == "KR":
        return f"{v / 1e12:.1f}조" if v >= 1e12 else (f"{v / 1e8:,.1f}억" if v >= 1e8 else f"{v / 1e4:,.0f}만")
    return f"${v / 1e6:.1f}M" if v >= 1e6 else f"${v / 1e3:,.0f}K"


def insider_week_items(rows: list[dict], tags: dict[str, list[str]], names: dict[str, str],
                       finance: dict[str, dict] | None = None) -> dict:
    """종목별로 묶는다: 산 사람 수(서로 다른 내부자)·합계 금액·건수·직함·최근 거래일.
    관심 표시가 있는 종목(items)과 관심 밖 새 이름(discovery, 2026-10-21)을 나눠 각각 산 사람 수 → 금액 순.
    관심 밖은 10b5-1 계획 매수만 있는 종목을 뒤로 - 미리 정해 둔 매수라 새 신호로 보기 어렵다.
    finance는 트랩 필터 3분류(통과/탈락/데이터부족 - watchlist_screening_results). 없으면 "미확인".
    공시 숫자를 그대로 더하고 정렬할 뿐 점수가 아니다(원칙 1)."""
    by: dict[str, dict] = {}
    for r in rows:
        key = f"{r['market']}:{r['symbol']}"
        g = by.setdefault(key, {"market": r["market"], "symbol": r["symbol"], "name": names.get(key), "owners": [],
                                "roles": [], "value": 0.0, "value_known": False, "trades": 0, "last_date": None,
                                "all_plan": True, "tags": tags.get(key, []), "finance": (finance or {}).get(key)})
        if r["owner"] not in g["owners"]:
            g["owners"].append(r["owner"])
            g["roles"].append(r.get("role") or "-")
        if r.get("value") is not None:
            g["value"] += float(r["value"])
            g["value_known"] = True
        g["trades"] += 1
        d = r.get("trade_date") or r.get("filed_on")
        if d and (g["last_date"] is None or d > g["last_date"]):
            g["last_date"] = d
        g["all_plan"] = g["all_plan"] and as_bool(r.get("plan"))
    groups = list(by.values())
    for g in groups:
        g["buyers"] = len(g["owners"])
        if not g["value_known"]:
            g["value"] = None
    tagged = sorted((g for g in groups if g["tags"]), key=lambda g: (-g["buyers"], -(g["value"] or 0)))
    other = sorted((g for g in groups if not g["tags"]), key=lambda g: (g["all_plan"], -g["buyers"], -(g["value"] or 0)))
    by_market: dict[str, int] = {}
    for g in groups:
        by_market[g["market"]] = by_market.get(g["market"], 0) + 1
    split = {m: {"tagged": sum(1 for g in tagged if g["market"] == m), "discovery": sum(1 for g in other if g["market"] == m)}
             for m in by_market}
    return {"total": len(groups), "by_market": by_market, "split_by_market": split, "items": tagged[:INSIDER_WEB_MAX],
            "tagged_count": len(tagged), "discovery": other[:INSIDER_WEB_MAX], "discovery_count": len(other)}


def screening_status(keys: set[str]) -> dict[str, dict]:
    """'시장:종목' -> 트랩 필터 3분류(watchlist_screening_results). 표가 없거나 대상 밖이면 빠진다(화면에서 "미확인")."""
    out: dict[str, dict] = {}
    try:
        for r in turso_exec("SELECT market, symbol, status, piotroski, red_flags FROM watchlist_screening_results"):
            key = f"{r['market']}:{r['symbol']}"
            if key not in keys:
                continue
            try:
                reasons = json.loads(r.get("red_flags") or "[]")
            except (TypeError, ValueError):
                reasons = []
            out[key] = {"status": r["status"], "piotroski": r.get("piotroski"),
                        "reasons": [x for x in reasons if isinstance(x, str)] if isinstance(reasons, list) else []}
    except Exception as e:  # noqa: BLE001
        logger.warning("트랩 필터 결과 조회 실패 - 재무 표시 없이: %s", e)
    return out


def interest_tags_names() -> tuple[dict[str, list[str]], dict[str, str]]:
    """'시장:종목' -> 관심 표시(my·note·cand·theme), 이름. 내부자 매수·미국 8-K 칸이 같이 쓴다."""
    tags: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    for sql, t in (("SELECT market, symbol, name FROM my_watchlist", "my"),
                   ("SELECT DISTINCT market, ticker AS symbol, NULL AS name FROM observations WHERE kind = 'stock' "
                    "AND ticker IS NOT NULL", "note"),
                   ("SELECT market, symbol, name FROM watchlist_candidates", "cand"),
                   ("SELECT DISTINCT m.market, m.ticker AS symbol, NULL AS name FROM theme_members m WHERE m.approved = 1 "
                    "AND m.run_id = (SELECT MAX(run_id) FROM theme_members t WHERE t.theme_id = m.theme_id "
                    "AND t.market = m.market AND t.approved = 1)", "theme")):
        try:
            for r in turso_exec(sql):
                key = f"{r['market']}:{r['symbol']}"
                if t not in tags.setdefault(key, []):
                    tags[key].append(t)
                if r.get("name"):
                    names.setdefault(key, r["name"])
        except Exception:  # noqa: BLE001
            pass
    try:   # 한국 이름은 유니버스 파일에서
        for i in json.loads(KR_UNIVERSE.read_text(encoding="utf-8")).get("items", []):
            names.setdefault(f"KR:{i['symbol']}", i.get("name"))
    except Exception:  # noqa: BLE001
        pass
    for path in US_LISTS:   # 미국 이름은 S&P 500·400 목록에서 - 관심 밖 새 이름도 회사명이 보이게
        try:
            with path.open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("Symbol"):
                        names.setdefault(f"US:{row['Symbol'].strip()}", row.get("Security"))
        except Exception:  # noqa: BLE001
            pass
    return tags, names


def get_insider_week() -> dict | None:
    """지난 7일 공시된 내부자 장내 매수(insider_trades, scripts/collect_insider_trades.py - 2026-10-21). 표가 없으면 None."""
    try:
        rows = turso_exec("SELECT market, symbol, owner, role, trade_date, filed_on, value, plan FROM insider_trades "
                          "WHERE filed_on >= date('now', '-7 days')")
    except Exception as e:  # noqa: BLE001
        logger.warning("내부자 매수 조회 실패(표 없음?) - 건너뜀: %s", e)
        return None
    tags, names = interest_tags_names()
    keys = {f"{r['market']}:{r['symbol']}" for r in rows}
    return insider_week_items(rows, tags, names, screening_status(keys))


US8K_TG_MAX = 5
US8K_WEB_MAX = 30


def us_8k_week_items(rows: list[dict], tags: dict[str, list[str]], names: dict[str, str]) -> dict:
    """미국 8-K 지난 7일 -> 목록. 실적 발표(2.02)만 있는 것은 뺀다(실적 발표 칸이 따로 있다).
    관심 표시 먼저 → 해지·손상·사임처럼 나쁜 쪽일 수 있는 종류 → 최근 순. 종류별 건수는 항목 이름(괄호 앞) 기준. 점수 없음(원칙 1)."""
    items, by_kind = [], {}
    for r in rows:
        d = json.loads(r["detail"]) if isinstance(r["detail"], str) else r["detail"]
        if d.get("earnings_only"):
            continue
        key = f"US:{r['symbol']}"
        shown = [x for x in d["items"] if x["item"] != "2.02"]
        for x in shown:
            base = x["label"].split("(")[0]
            by_kind[base] = by_kind.get(base, 0) + 1
        items.append({"market": "US", "symbol": r["symbol"], "name": names.get(key), "date": r["filed_on"],
                      "url": r.get("url"), "tags": tags.get(key, []), "warn": bool(d.get("warn")), "items": shown})
    items.sort(key=lambda x: x["date"], reverse=True)
    items.sort(key=lambda x: (not x["tags"], not x["warn"]))
    return {"total": len(items), "by_kind": dict(sorted(by_kind.items(), key=lambda kv: -kv[1])),
            "items": items[:US8K_WEB_MAX]}


def get_us_8k_week() -> dict | None:
    """지난 7일 미국 8-K(us_8k_filings, scripts/collect_us_8k.py - 2026-10-21). 표가 없으면 None."""
    try:
        rows = turso_exec("SELECT symbol, filed_on, detail, url FROM us_8k_filings WHERE filed_on >= date('now', '-7 days')")
    except Exception as e:  # noqa: BLE001
        logger.warning("미국 8-K 조회 실패(표 없음?) - 건너뜀: %s", e)
        return None
    tags, names = interest_tags_names()
    return us_8k_week_items(rows, tags, names)


INST_WEB_MAX = 10
INST_TG_MANAGERS = 4
INST_TG_NAMES = 4


def load_institutions() -> dict[str, dict]:
    try:
        return {m["id"]: m for m in yaml.safe_load((ROOT / "config" / "institutions.yaml").read_text(encoding="utf-8"))["managers"]}
    except Exception:  # noqa: BLE001
        return {}


def inst_13f_week_items(filings: list[dict], rows: list[dict], meta: dict[str, dict], tags: dict[str, list[str]],
                        names: dict[str, str], screen: dict[str, dict]) -> dict:
    """유명 투자자 13F(2026-10-25) - 지난 7일 신고한 운용사마다 그 분기에 새로 산 종목·다 판 종목(평가액 순, 신고서 값 그대로).
    rows: inst_13f_positions(주식만)에서 그 운용사·분기의 new/added/reduced/sold 줄. 관심 표시 종목 줄은 tagged에 전부 모은다(⭐ 칸용).
    점수·순위 없음(원칙 1). 재무는 트랩 필터 3분류(원칙 4)."""
    items, tagged = [], []
    for f in filings:
        mine = [r for r in rows if r["manager_id"] == f["manager_id"] and r["period"] == f["period"]]
        m = meta.get(f["manager_id"], {})

        def row(r: dict) -> dict:
            key = f"US:{r['ticker']}" if r.get("ticker") else None
            return {"ticker": r.get("ticker"), "issuer": r.get("issuer"), "name": names.get(key) if key else None,
                    "value": r.get("value"), "prev_value": r.get("prev_value"), "weight": r.get("weight"), "status": r.get("status"),
                    "share_chg": r.get("share_chg"), "tags": tags.get(key, []) if key else [],
                    "finance": screen.get(key) if key else None}
        new = sorted((row(r) for r in mine if r["status"] == "new"), key=lambda x: -(x["value"] or 0))
        sold = sorted((row(r) for r in mine if r["status"] == "sold"), key=lambda x: -(x["prev_value"] or 0))
        counts = {k: sum(1 for r in mine if r["status"] == k) for k in ("new", "added", "reduced", "sold")}
        full = f"{m['ko']} · {m['person']}" if m.get("ko") and m.get("person") else m.get("ko", f["manager_id"])   # 운용사 · 대표 인물(2026-11-02)
        items.append({"manager_id": f["manager_id"], "name": full, "style": m.get("style"),
                      "period": f["period"], "filed": f["filed"], "counts": counts, "compared": any(r["status"] for r in mine),
                      "new": new[:INST_WEB_MAX], "sold": sold[:INST_WEB_MAX]})
        for r in mine:
            x = row(r)
            if x["tags"] and r["status"] in ("new", "added", "reduced", "sold"):
                tagged.append({**x, "manager_id": f["manager_id"], "manager": m.get("ko", f["manager_id"]), "period": f["period"]})
    items.sort(key=lambda x: x["filed"], reverse=True)
    return {"filers": len(items), "items": items, "tagged": tagged}


def get_inst_13f_week() -> dict | None:
    """지난 7일에 13F를 낸 운용사(inst_13f_filings, scripts/collect_13f.py). 낸 곳이 없거나 표가 없으면 None - 칸을 숨긴다."""
    try:
        filings = turso_exec("SELECT manager_id, period, MAX(filed_on) AS filed FROM inst_13f_filings "
                             "WHERE filed_on >= date('now', '-7 days') GROUP BY manager_id, period")
    except Exception as e:  # noqa: BLE001
        logger.warning("13F 조회 실패(표 없음?) - 건너뜀: %s", e)
        return None
    if not filings:
        return None
    rows = []
    for f in filings:
        rows += turso_exec("SELECT manager_id, period, ticker, issuer, value, prev_value, weight, status, share_chg FROM inst_13f_positions "
                           "WHERE manager_id = ? AND period = ? AND put_call = '' AND status IN ('new', 'added', 'reduced', 'sold')",
                           [f["manager_id"], f["period"]])
    tags, names = interest_tags_names()
    keys = {f"US:{r['ticker']}" for r in rows if r.get("ticker") and r["status"] in ("new", "added")}
    return inst_13f_week_items(filings, rows, load_institutions(), tags, names, screening_status(keys))


def get_kr_disclosures_week() -> dict | None:
    """한국 공시 지난 7일(kr_disclosures, scripts/collect_kr_disclosures.py - 2026-10-17). 표가 없으면 None."""
    try:
        rows = turso_exec("SELECT rcept_no, rcept_dt, stock_code, corp_name, kind, payload FROM kr_disclosures "
                          "WHERE kind IN ('contract', 'prelim', 'termination', 'amend') AND rcept_dt >= date('now', '+9 hours', '-7 days')")
    except Exception as e:  # noqa: BLE001
        logger.warning("한국 공시 조회 실패(표 없음?) - 건너뜀: %s", e)
        return None
    try:
        universe = {i["symbol"] for i in json.loads(KR_UNIVERSE.read_text(encoding="utf-8")).get("items", [])}
    except Exception:  # noqa: BLE001 - 유니버스 파일이 없으면 관심 종목만
        universe = set()
    tags: dict[str, list[str]] = {}
    for sql, t in (("SELECT symbol FROM my_watchlist WHERE market = 'KR'", "my"),
                   ("SELECT DISTINCT ticker AS symbol FROM observations WHERE kind = 'stock' AND market = 'KR' "
                    "AND ticker IS NOT NULL", "note"),
                   ("SELECT symbol FROM watchlist_candidates WHERE market = 'KR'", "cand"),
                   # 테마 소속 - 테마마다 가장 최근 승인 run(get_approved_theme_members와 같은 기준)
                   ("SELECT DISTINCT m.ticker AS symbol FROM theme_members m WHERE m.market = 'KR' AND m.approved = 1 "
                    "AND m.run_id = (SELECT MAX(run_id) FROM theme_members t WHERE t.theme_id = m.theme_id "
                    "AND t.market = 'KR' AND t.approved = 1)", "theme")):
        try:
            for r in turso_exec(sql):
                if r.get("symbol") and t not in tags.setdefault(r["symbol"], []):
                    tags[r["symbol"]].append(t)
        except Exception:  # noqa: BLE001
            pass
    return kr_disclosures_week(rows, universe, tags)


def get_sentiment_week(week: str) -> list[dict]:
    """이번 주 관심도 기록이 그 전 마지막 기록보다 올라간 종목.
    관심도는 주간 네러티브 생성 때 주 1회 적힌다 - 예전에는 '최근 7일 안의 첫 값 vs 마지막 값'이라 지난주 기록이 정확히 7일 전에 있어야만
    잡혔다(예약 실행이 자정을 넘겨 늦게 돌면 빈 칸). 워치리스트 ▲관심 배지와 같은 '그 전 마지막 기록' 비교로 바꿨다(2026-10-21).
    '이번 주' = 신호 기록과 같은 sentiment_window(월요일-6일 ~ 월요일) - '지금-7일'이면 지난주 실행이 월요일 날짜로 적힌 주에
    지난주 기록까지 이번 주로 들어가 2주 전 값과 비교됐다(2026-10-26)."""
    rows = turso_exec(
        "SELECT market, symbol, date, sentiment FROM narrative_sentiment_history "
        "WHERE date >= date('now', '-35 days') ORDER BY market, symbol, date"
    )
    cut = sentiment_window(week)[0]
    before: dict[str, str] = {}
    within: dict[str, str] = {}
    for r in rows:
        key = f"{r['market']}:{r['symbol']}"
        (within if str(r["date"])[:10] >= cut else before)[key] = r["sentiment"]

    # 이름 조회
    names = {f"{c['market']}:{c['symbol']}": c.get("name")
             for c in turso_exec("SELECT market, symbol, name FROM watchlist_candidates")}

    heating = []
    for key, now in within.items():
        prev = before.get(key)
        if prev is not None and SENTIMENT_RANK.get(now, 1) > SENTIMENT_RANK.get(prev, 1):
            market, symbol = key.split(":", 1)
            heating.append({
                "market": market, "symbol": symbol, "name": names.get(key),
                "path": f"{SENTIMENT_KO.get(prev, prev)}→{SENTIMENT_KO.get(now, now)}",
            })
    return heating[:10]


def get_theme_label_changes() -> dict:
    """테마 레이더 라벨 변동 - 시장별로 계산된 가장 최근 두 주 비교 (미국·한국).

    라벨 계산(compute-theme-labels.yml)은 이 브리핑과 별도 워크플로라 "이번 주"라고 단정하지 않고
    실제로 계산이 끝난 week_start를 그대로 노출한다. 항목마다 market을 붙인다(2026-10-05 한국 추가 -
    예전엔 미국만 봤다). label_counts는 시장별 이번 주 라벨 수 - 0이면 텔레그램에 "아직 라벨 없음"을 쓴다.
    """
    out = {"week_start": None, "new_labels": [], "dropped_labels": [], "label_counts": {}}
    for market in ("US", "KR"):
        weeks = turso_exec(
            "SELECT DISTINCT week_start FROM theme_signals WHERE market = ? "
            "ORDER BY week_start DESC LIMIT 2", [market]
        )
        if not weeks:
            continue
        latest = weeks[0]["week_start"]
        out["week_start"] = max(out["week_start"] or latest, latest)

        def labels(week: str) -> dict[str, str]:
            rows = turso_exec(
                "SELECT theme_id, label FROM theme_signals "
                "WHERE market = ? AND week_start = ? AND label IS NOT NULL",
                [market, week],
            )
            return {r["theme_id"]: r["label"] for r in rows}

        cur_map = labels(latest)
        prev_map = labels(weeks[1]["week_start"]) if len(weeks) > 1 else {}
        out["label_counts"][market] = len(cur_map)
        out["new_labels"] += [{"theme_id": t, "label": l, "market": market}
                              for t, l in cur_map.items() if prev_map.get(t) != l]
        out["dropped_labels"] += [{"theme_id": t, "label": l, "market": market}
                                  for t, l in prev_map.items() if t not in cur_map]
    return out


EXPECT_KO = {
    "theme": {"news_up": "뉴스↑", "news_down": "뉴스↓", "earn_up": "실적↑", "earn_down": "실적↓",
              "price_up": "주가↑", "price_down": "주가↓", "earn_hold": "실적↑ 유지"},
    "stock": {"news_up": "테마 뉴스↑", "news_down": "테마 뉴스↓", "earn_up": "실적 초과", "earn_down": "실적 미달",
              "price_up": "지수보다 더 오름", "price_down": "지수보다 덜 오름", "earn_hold": "실적 유지"},
}


def get_observation_reviews() -> list[dict]:
    """지난 8일 안에 붙었고 아직 판단하지 않은 관찰 노트 회고 (scripts/review_observations.py). 표가 없으면 빈 목록."""
    try:
        rows = turso_exec(
            "SELECT o.kind, o.market, o.theme_id, o.ticker, o.created_at, r.checkpoint, r.expect_results "
            "FROM observation_reviews r JOIN observations o ON o.id = r.observation_id "
            # 아직 판단 안 한 것만 - 브리핑과 회고 작업의 실행 순서에 따라 같은 회고가 두 주 연속 잡힐 수 있어서,
            # 판단을 남긴 회고는 다시 알리지 않는다. reviewed_at은 ISO('T' 구분)라 공백 형식으로 바꿔 비교한다.
            "WHERE r.verdict IS NULL AND REPLACE(r.reviewed_at, 'T', ' ') >= datetime('now', '-8 days') "
            "ORDER BY r.reviewed_at DESC LIMIT 10"
        )
    except Exception:
        return []
    out = []
    for r in rows:
        try:
            results = json.loads(r.get("expect_results") or "{}")
        except Exception:
            results = {}
        out.append({**r, "expect_results": results})
    return out


# ── GPT 총평 ─────────────────────────────────────────────────────────────────

# ── 주간 총평 (GPT) ─────────────────────────────────────────────────────────
# 2026-11-02 사용자 요청: 총평이 너무 평이하다 - 더 구체적으로. 예전엔 지수 2개·워치리스트 이름·관심도만 넘겨서 일반론밖에 못 썼다.
# 이제 브리핑에 이미 있는 내용(매크로·수급·종목 변화·테마 라벨·공시·내부자·13F·이번 주 실적 발표·내 관심 종목)을 넘기되,
# 숫자는 코드가 먼저 말로 바꾼다(qual_*) - LLM은 숫자를 받지도 쓰지도 않는다(원칙 2). 그래도 숫자가 섞이면 그 문장을 뺀다(strip_numeric_sentences).

def qual_pct(v: float | None, big: float = 3.0, mid: float = 1.0, small: float = 0.3) -> str | None:
    """등락률(%) -> '큰 폭 상승' / '상승' / '소폭 상승' / '보합' ... 판정이 아니라 크기를 말로."""
    if v is None:
        return None
    a, up = abs(v), v > 0
    if a < small:
        return "보합"
    word = "큰 폭 " if a >= big else "" if a >= mid else "소폭 "
    return word + ("상승" if up else "하락")


def qual_macro(key: str, item: dict | None) -> str | None:
    """매크로 1주 변화 -> 말. 금리·스프레드는 %p, 환율은 원, 달러인덱스는 포인트, 원자재는 변화율로 크기를 나눈다."""
    if not item or item.get("value") is None or item.get("chg_1w") is None:
        return None
    v, c = float(item["value"]), float(item["chg_1w"])
    if key == "vix":
        return qual_pct(c, big=3.0, mid=1.0, small=0.3)            # VIX 포인트: 3 이상 큰 폭, 1 이상, 0.3 미만 보합
    if key in ("us10y", "kr3y", "real10y", "hy_spread", "spread_10y_2y"):
        return qual_pct(c * 10, big=1.5, mid=0.5, small=0.2)      # 0.15%p 이상 큰 폭, 0.05%p 이상, 0.02%p 미만 보합
    if key == "usdkrw":
        return qual_pct(c / 10, big=2.0, mid=0.5, small=0.2)      # 20원 큰 폭, 5원, 2원 미만 보합
    if key == "dxy":
        return qual_pct(c, big=1.5, mid=0.5, small=0.2)
    base = v - c
    return qual_pct(c / base * 100 if base else None)              # 유가·구리·천연가스: 변화율


def qual_flow(v: float | None) -> str | None:
    if v is None:
        return None
    a = abs(v)
    size = "큰 폭 " if a >= 1e12 else "" if a >= 2e11 else "소폭 "
    return size + ("순매수" if v > 0 else "순매도")


_NUM_RE = re.compile(r"\d[\d,]*(\.\d+)?\s*(%|%p|억|조|원|달러|bp|배|포인트)|\$\s?\d")


def strip_numeric_sentences(text: str) -> str:
    """수치(%·억·원·$ 등)가 들어간 문장을 뺀다 - 숫자는 화면에 따로 있고 LLM이 만든 숫자는 쓰지 않는다(원칙 2).
    '13F'·'8-K'처럼 숫자가 든 이름은 단위가 없어 남는다."""
    out = []
    for line in text.split("\n"):
        parts = re.split(r"(?<=[.!?。다요])\s+", line)
        kept = [p for p in parts if not _NUM_RE.search(p)]
        out.append(" ".join(kept).strip() if not line.startswith("■") else line)
    return "\n".join(out).strip()


# 라벨 뜻(theme_labels._RULES의 뉴스·실적·주가 조합) - GPT가 이름만 보고 뜻을 짐작하지 않게 같이 넘긴다
LABEL_KO_SHORT = {"Early Buzz": "뉴스 선행", "Full Alignment": "동반 상승", "Quiet Strength": "숨은 강세",
                  "Overheated Buzz": "기대 과열", "Full Decline": "동반 하락", "Quiet Recovery": "숨은 회복"}
LABEL_MEANING = {
    "Early Buzz": "뉴스가 크게 늘고 주가도 올랐지만 실적은 아직 그대로 - 기대가 먼저 움직임",
    "Full Alignment": "뉴스·실적·주가가 모두 오름",
    "Quiet Strength": "실적은 크게 좋아졌는데 뉴스는 조용하고 주가도 아직 그대로 - 시장이 덜 본 개선",
    "Overheated Buzz": "뉴스와 주가는 크게 올랐는데 실적은 나빠짐 - 기대가 실적보다 앞섬",
    "Full Decline": "뉴스·실적·주가가 모두 내림",
    "Quiet Recovery": "뉴스와 주가는 내렸는데 실적은 좋아짐 - 눈에 덜 띄는 회복",
}


_CORP_SUFFIX = re.compile(r",?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.|PLC|plc|Ltd\.?|N\.V\.|S\.A\.|AG|SE)$")


def _clean_names(xs) -> list[str]:
    """이름 끝의 쉼표·공백을 지우고 같은 이름은 한 번만(같은 회사 공시 두 건 등)."""
    out: list[str] = []
    for x in xs:
        x = (x or "").replace("(The)", "").strip().rstrip(",").strip()
        while (y := _CORP_SUFFIX.sub("", x)) != x:   # 'AMETEK, Inc.'·'Eaton Corporation, PLC' → 'AMETEK'·'Eaton' (글로 읽기 편하게)
            x = y.strip().rstrip(",").strip()
        if x and x not in out:
            out.append(x)
    return out


# 총평에 넘길 때만 쓰는 8-K 설명 - 화면 이름 '상장 유지 기준 미달·이전'은 짧게 줄인 말이라 GPT가 "기준 미달로 이전"처럼 잘못 이었다(11/2 미리 보기).
# 3.01은 상장폐지 통보·기준 미달·거래소 이전을 한 항목에 묶으므로 어느 쪽인지 단정하지 않게 쓴다.
COMMENT_8K = {"3.01": "상장 관련 통지(상장 기준 미달 통보 또는 거래소 이전 - 어느 쪽인지는 공시 본문 확인 필요)"}

# 데이터에 없는 효과를 짐작한 문장(11/2 미리 보기: "기관 순매수가 지수에 긍정적인 영향을 미쳤을 것") - 프롬프트로 막아도 새어 나와 코드로 뺀다
_SPECULATION_RE = re.compile(r"영향을\s*(미쳤|미친|미칠|줬|준|줄|주었)|(긍정적|부정적|우호적|호재|악재)(인|으로|이다|입니다)?|기여(했|한|할)|덕분|때문|끌어올|끌어내|견인|이끌|이로 인해|그로 인해|그 결과|시사(한다|하는|했다)|보여준다|의미한다|방증"
                             r"|주목할\s*만|눈여겨볼|(^|\s)이는\s|미칠\s*영향"
                             r"|주목(받|된|되|을\s*받|할\s*(일정|대목|부분))|관심을\s*끌|기대를\s*모"
                             r"|불안감|불안\s*심리|투자\s*심리|심리가\s*(위축|개선|악화)"
                             r"|힘입|(으로|로)\s*인(한|해)\s")   # 11/7 미리 보기: "매수세에 힘입어", "환율 급락으로 인한 영업이익 감소"
# ↑ 11/5 미리 보기: "이는 주목할 만한 변화이다", "매출 감소가 실적에 미칠 영향" / 11/7 월간 보고서: "주목할 일정이다", "주목받았다"
#   11/7 미리 보기: "시장의 불안감을 드러냈다"

# 한국어 조사: 받침 있는 말 뒤 / 없는 말 뒤
_PARTICLES = (("이", "가"), ("은", "는"), ("을", "를"), ("과", "와"))


def _has_batchim(ch: str) -> bool | None:
    o = ord(ch)
    return (o - 0xAC00) % 28 != 0 if 0xAC00 <= o <= 0xD7A3 else None


def fix_names(text: str, names: list[str]) -> str:
    """GPT가 고유명사 끝 글자를 빠뜨린 것(큐리옥스바이오시스템즈 → …시스템)을 데이터의 이름으로 되돌리고, 뒤 조사를 받침에 맞춘다.
    본래 이름이 글에 한 번도 없고, 끝 한두 글자만 뺀 꼴(네 글자 이상)이 있을 때만 - 다른 이름의 일부면 건드리지 않는다."""
    for name in sorted(set(names), key=len, reverse=True):
        if len(name) < 5 or name in text:
            continue
        for cut in (1, 2):
            short = name[:-cut]
            if len(short) < 4 or short not in text or any(short in o for o in names if o != name):
                continue
            def rep(m: re.Match) -> str:
                p = m.group(1)
                b = _has_batchim(name[-1])
                for with_b, without_b in _PARTICLES:
                    if b is not None and p in (with_b, without_b):
                        p = with_b if b else without_b
                return name + p
            text = re.sub(re.escape(short) + r"(이|가|은|는|을|를|과|와)?", lambda m: rep(m) if m.group(1) else name, text)
            break
    return text


def strip_speculation(text: str) -> str:
    """효과·원인을 짐작한 문장을 뺀다(소제목 줄은 남김). 원칙: 데이터에 없는 사실을 만들지 않는다."""
    out = []
    for line in text.split("\n"):
        if line.startswith("■"):
            out.append(line)
            continue
        parts = re.split(r"(?<=[.!?。다요])\s+", line)
        out.append(" ".join(p for p in parts if not _SPECULATION_RE.search(p)).strip())
    return "\n".join(out).strip()


def _fact_names(facts: dict) -> list[str]:
    """사실 묶음에 든 이름(종목·테마) - 'X: …'·'X (…)'·'X - …' 꼴은 앞 이름만."""
    out = []
    for k, v in facts.items():
        if not isinstance(v, list):
            continue
        for x in v:
            if "8-K" in k:   # 'GM 상장 관련 통지(…)' - 앞 티커만
                out.append(x.split(" ", 1)[0])
                continue
            out.append(re.split(r"\s*(?::|\s\(|\(|\s-\s)", x, maxsplit=1)[0].strip())
    return [n for n in out if n]


def polish_comment(text: str, facts: dict) -> str:
    """GPT 글 뒷손질: 소제목 줄 분리 → 이름 되돌리기 → 짐작 문장 빼기 → 수치 문장 빼기."""
    return strip_numeric_sentences(strip_speculation(fix_names(split_headings(text), _fact_names(facts))))


def split_headings(text: str) -> str:
    """'■ 시장 - 본문…'처럼 소제목 줄에 본문이 붙어 나오면 두 줄로 나눈다 - 화면은 ■ 줄 전체를 소제목으로 그린다."""
    out = []
    for line in text.split("\n"):
        m = re.match(r"^(■\s*[^-:：\n]{1,20}?)\s*[-:：]\s+(.+)$", line.strip())
        out += [m.group(1).strip(), m.group(2).strip()] if m else [line.rstrip()]
    return "\n".join(out)


def comment_facts(b: dict) -> dict:
    """GPT에 넘길 사실 묶음 - 이름·종류·말로 바꾼 크기만(숫자 없음). 빈 칸은 빼서 쓸 거리가 없는 문단을 만들지 않게.
    목록은 대표만 몇 개 - 다 넘기면 GPT가 문장 대신 목록을 그대로 옮겨 적는다(전체 목록은 화면 각 칸에 있다)."""
    mc = b.get("macro") or {}
    names = load_theme_names()
    macro_ko = {"us10y": "미 10년물 금리", "real10y": "미 실질금리", "hy_spread": "하이일드 스프레드", "kr3y": "국고채 3년",
                "usdkrw": "원/달러 환율", "dxy": "달러인덱스", "wti": "WTI 유가", "copper": "구리", "natgas": "천연가스",
                "vix": "VIX(미국 변동성지수)", "spread_10y_2y": "미 장단기 금리차(10년-2년)"}
    flows = b.get("kr_flows") or {}
    market = {
        "미국 지수(S&P 500) 1주": qual_pct(b["us"].get("index_chg_1w")),
        "한국 지수(KOSPI) 1주": qual_pct(b["kr"].get("index_chg_1w")),
        **{f"{ko} 1주": qual_macro(k, mc.get(k)) for k, ko in macro_ko.items()},
        **{f"{m} {who} 5거래일": qual_flow((flows.get(m) or {}).get(key)) for m in ("KOSPI", "KOSDAQ")
           for key, who in (("foreign", "외국인"), ("institution", "기관"))},
    }
    nm = lambda x: x.get("name") or x.get("symbol")  # noqa: E731
    mk_ko = {"US": "미국", "KR": "한국"}

    def lab(t: dict) -> str:   # 라벨 뜻을 항목에 바로 붙인다 - 따로 두면 GPT가 이름만 늘어놓고 뜻을 빼먹었다(11/2 미리 보기)
        head = f"{names.get(t['theme_id'], t['theme_id'])}({mk_ko.get(t.get('market'), '')}) - {label_display(t['label'])}"
        return head + (f": {LABEL_MEANING[t['label']]}" if t["label"] in LABEL_MEANING else "")
    wl = b.get("watchlist") or {}
    ta = b.get("turnaround") or {}
    tl = b.get("theme_labels") or {}
    kd = b.get("kr_disclosures") or {}
    ins = b.get("insider_week") or {}
    u8 = b.get("us_8k_week") or {}
    inst = b.get("inst_13f_week") or {}
    ew = b.get("earnings_week") or {}
    my = b.get("my_stocks_week") or {}
    # 시장 환경 축(2026-11-07) - 정해진 조합 이름과 축별 방향을 말로. GPT가 지표 숫자를 제멋대로 엮지 않고 같은 틀로 쓰게
    from src.analyzers.regime import describe as regime_describe
    for st in (b.get("regime") or {}).values():
        market.update(regime_describe(st))
    facts = {
        "시장": {k: v for k, v in market.items() if v},
        "내 관심 종목에 생긴 일": [f"{nm(x)}: " + ", ".join(e["kind"] for e in x["events"]) for x in (my.get("items") or [])[:8]],
        "워치리스트 새로 들어온 종목": [nm(a) for a in (wl.get("added") or [])[:10]] if wl.get("has_prev") else [],
        "워치리스트에서 빠진 종목": [nm(a) for a in (wl.get("removed") or [])[:10]] if wl.get("has_prev") else [],
        "실적 반전(3년 정체·역성장인데 최근 성장) 새로 들어온 종목": [nm(a) for a in (ta.get("added") or [])[:5]],
        "관심도 상승 종목": [f"{nm(h)} ({h['path']})" for h in (b.get("sentiment_heating") or [])[:5]],
        "새로 붙은 테마 라벨": [lab(t) for t in (tl.get("new_labels") or [])[:8]],
        "사라진 테마 라벨": [lab(t) for t in (tl.get("dropped_labels") or [])[:8]],
        "한국 공시 - 계약 해지": [nm(x) for x in ((kd.get("termination") or {}).get("items") or [])[:5]],
        "한국 공시 - 매출 대비 큰 공급계약(10% 이상)": [nm(x) for x in ((kd.get("contract") or {}).get("items") or []) if (x.get("pct") or 0) >= 10][:8],
        "한국 잠정실적 - 흑자·적자 전환": [f"{nm(x)} 영업이익 {x.get('operating_income_yoy_turn')}" for x in ((kd.get("prelim") or {}).get("items") or [])
                                if x.get("operating_income_yoy_turn")][:8],
        "내부자 매수 - 여러 명이 함께 산 종목": [nm(g) for g in (ins.get("items") or []) + (ins.get("discovery") or [])
                                   if g.get("buyers", 0) > 1 and not g.get("all_plan")][:8],
        "미국 8-K 주의 공시": [f"{x['symbol']} " + ", ".join(COMMENT_8K.get(i.get("item"), i["label"]) for i in x["items"] if i.get("warn"))
                          for x in (u8.get("items") or []) if x.get("warn")][:4],
        "13F 이번 주 신고 운용사와 신규 매수 상위": [f"{it['name']}: " + ", ".join((p.get("ticker") or p.get("issuer") or "?") for p in it["new"][:3])
                                       for it in (inst.get("items") or [])[:6]],
        "이번 주 실적 발표(관심 종목)": [f"{nm(x)}" for x in (ew.get("items") or []) if x.get("tags")][:6],
    }
    facts = {k: (_clean_names(v) if isinstance(v, list) else v) for k, v in facts.items()}
    return {k: v for k, v in facts.items() if v}





def get_theme_members() -> dict[tuple[str, str], set[str]]:
    """(시장, 테마) -> 소속 종목 - 테마마다 가장 최근 승인 run(interest_tags_names의 'theme'과 같은 기준). 실패하면 빈 표."""
    out: dict[tuple[str, str], set[str]] = {}
    try:
        for r in turso_exec("SELECT m.market, m.theme_id, m.ticker FROM theme_members m WHERE m.approved = 1 "
                            "AND m.run_id = (SELECT MAX(run_id) FROM theme_members t WHERE t.theme_id = m.theme_id "
                            "AND t.market = m.market AND t.approved = 1)"):
            out.setdefault((r["market"], r["theme_id"]), set()).add(r["ticker"])
    except Exception:  # noqa: BLE001
        pass
    return out


def comment_points(b: dict) -> list[dict]:
    """총평의 '이번 주 짚을 점' - 칸과 칸 사이에서 겹치거나 엇갈리는 사실(src/analyzers/briefing_points.py) + 관련 기사."""
    from src.analyzers.briefing_points import find_points
    tags, names = interest_tags_names()
    mine = {k for k, v in tags.items() if any(t in MY_TAGS for t in v)}
    members = get_theme_members()
    points = find_points(b, load_theme_names(), members, mine, COMMENT_8K, qual_macro)
    try:
        attach_news(points, b, members, names)
    except Exception as e:  # noqa: BLE001 - 기사는 덧붙이는 것이라 실패해도 총평은 만든다
        logger.warning("짚을 점 관련 기사 실패: %s", type(e).__name__)
    return points


def _theme_news_rows(theme_id: str, markets: list[str], week: str) -> list[dict]:
    if not markets or not week:
        return []
    marks = ",".join("?" for _ in markets)
    return turso_exec(f"SELECT title, url, source, published_at FROM theme_news WHERE theme_id = ? AND market IN ({marks}) "
                      f"AND week_start = ? ORDER BY published_at DESC LIMIT 400", [theme_id, *markets, week])


def _stock_news_rows(market: str, name: str, after, before) -> list[dict]:
    from src.collectors.theme_news_collector import naver_credentials, search_google_news_en, search_google_news_kr, search_naver_news_kr
    if market == "KR":
        if naver_credentials():
            return list(search_naver_news_kr(name, after, before, limit=60))
        return search_google_news_kr(f'"{name}"', after, before, limit=60)
    return search_google_news_en(f'"{name}"', after, before, limit=60)


CORE_KEYWORDS = 2   # 키워드 목록 앞 두 개가 테마의 핵심어(석유화학·에틸렌 스프레드) - 뒤쪽(정제마진)은 곁가지


def theme_keywords(theme_id: str, markets: list[str]) -> tuple[list[str], list[str]]:
    """themes.yaml 검색 키워드(한국 keywords_ko, 미국 keywords_en)를 (핵심, 곁가지)로. 기사 고를 때 핵심어가 든 제목을 먼저
    (2026-11-05: 석유화학 테마에 BP 정제마진 기사가 붙었다 - 테마 정의는 정유를 일부러 포함하므로 정의는 두고 고르는 순서만)."""
    try:
        cfg = yaml.safe_load((ROOT / "config" / "themes.yaml").read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return [], []
    for t in cfg.get("themes") or []:
        if t.get("id") == theme_id:
            core, minor = [], []
            for mk, field in (("KR", "keywords_ko"), ("US", "keywords_en")):
                if mk in markets:
                    kws = [k for k in (t.get(field) or []) if k]
                    core += kws[:CORE_KEYWORDS]
                    minor += kws[CORE_KEYWORDS:]
            return core, minor
    return [], []


def attach_news(points: list[dict], b: dict, members: dict, names: dict[str, str]) -> None:
    """짚을 점마다 point["news"] = 관련 기사 최대 3개(src/analyzers/briefing_news.py). 테마는 theme_news(새 수집 없음),
    종목은 이름으로 그 주 기사 검색. 하나가 실패해도 나머지는 붙인다."""
    from src.analyzers.briefing_news import pick_headlines
    tl_week = (b.get("theme_labels") or {}).get("week_start")
    week = datetime.strptime(b["week"], "%Y-%m-%d").date()
    after, before = week - timedelta(days=7), week + timedelta(days=1)
    for p in points:
        try:
            if p.get("theme_id"):
                mk = p.get("markets") or []
                member_names = _clean_names(names.get(f"{m}:{sym}") or "" for m in mk for sym in members.get((m, p["theme_id"])) or [])
                rows = _theme_news_rows(p["theme_id"], mk, tl_week)
                core, minor = theme_keywords(p["theme_id"], mk)
                p["news"] = pick_headlines(rows, _clean_names(p.get("signal_names") or []), member_names,
                                           keywords=core, minor_keywords=minor)
            elif p.get("symbol"):
                nm = (_clean_names([p.get("title_name") or ""]) or [p["symbol"]])[0]
                rows = _stock_news_rows(p.get("market") or "US", nm, after, before)
                p["news"] = pick_headlines(rows, [nm], must_contain=nm if p.get("market") == "KR" else None)
        except Exception as e:  # noqa: BLE001
            logger.warning("관련 기사 실패(%s): %s", p.get("title"), type(e).__name__)


_LAST_RAW_COMMENT = [""]


_SE_BOINDA = {"였다": "했다", "인": "한", "이며": "하며", "이고": "하고", "여": "해"}


def fix_passive(text: str) -> str:
    """금지해도 가끔 새는 번역투를 기사체로(11/2·11/3 미리 보기):
    "'숨은 강세'로 분류됐다" → "'숨은 강세' 라벨이 붙었다", "하락세를 보인 반면" → "하락한 반면", "미국의 경우" → "미국은"."""
    text = re.sub(r"'([^']+)'(?:으)?로 분류(?:됐|되었)다", r"'\1' 라벨이 붙었다", text)
    text = re.sub(r"(상승|하락)세를 보(였다|인|이며|이고|여)", lambda m: m.group(1) + _SE_BOINDA[m.group(2)], text)
    text = re.sub(r"보합세를 보(였다|인|이며|이고)", lambda m: "보합" + {"였다": "이었다", "인": "인", "이며": "이며", "이고": "이고"}[m.group(1)], text)
    # "시장이 엇갈린 흐름을 보였다" → "시장이 엇갈렸다"(11/7 미리 보기) - 주어 조사 바로 뒤일 때만(앞 말이 꾸미는 꼴은 손대지 않음)
    # 주어 조사 이/가 뒤나 연결 어미(~며·~서·~고) 뒤일 때만 - '줄어드는 엇갈린 신호'처럼 꾸미는 꼴은 손대지 않음
    text = re.sub(r"((?:며|서|고|[가-힣A-Za-z0-9][이가])\s+)(?:엇갈린\s+(?:흐름|신호|모습)(?:을|를)|혼조세를)\s+(?:보였|나타냈)다",
                  r"\1엇갈렸다", text)
    # "~붙었고, 이는 4주 전 '…'이라고 적어 둔 기대가 맞았다"(11/7 미리 보기) - '이는'이 짐작 거르기에 걸려 핵심 문장이 통째로 지워졌다.
    # 관찰 노트 결과를 받는 '이는'만 떼어 사실 문장으로 남긴다(다른 '이는 ~을 시사한다' 꼴은 그대로 걸러진다)
    text = re.sub(r",\s*이는\s+(?=[^.]{0,80}기대)", ", ", text)
    text = re.sub(r"(^|(?<=\.\s))이는\s+(?=[^.]{0,80}기대)", "", text)
    # 평가 말투(11/5 미리 보기 "Intel의 내부자 매수도 주목할 만하다") - 사실만 남긴다
    text = re.sub(r"도 (주목할 만하다|주목된다|눈에 띈다|눈길을 끈다)\.", "도 있었다.", text)

    def keyeong(m: re.Match) -> str:
        w = m.group(1)
        b = _has_batchim(w[-1])
        return w + ("은" if b else "는") if b is not None else m.group(0)
    return re.sub(r"([가-힣A-Za-z0-9·]+)의 경우(?!에),?", keyeong, text)


def assemble_comment(market: str, bodies: list, points: list[dict]) -> str:
    """소제목은 코드가 붙인다(GPT가 제목을 바꾸지 못하게). 본문이 비면(실패·전부 걸러짐) 사실을 그대로 잇는다.
    bodies 항목은 글 또는 {"body", "next"} - next(이어서 볼 것)는 '→ 이어서 볼 것:' 줄로 붙인다."""
    names = [p.get("title_name") or "" for p in points] + [f.split(":")[0] for p in points for f in p["facts"]]
    clean = lambda t: strip_numeric_sentences(strip_speculation(fix_names(fix_passive(t or ""), [n for n in names if n])))  # noqa: E731
    out = []
    if (m := clean(market)):
        out += ["■ 시장 분위기", m, ""]
    for i, p in enumerate(points):
        item = bodies[i] if i < len(bodies) else ""
        text, nxt = (str(item.get("body") or ""), str(item.get("next") or "")) if isinstance(item, dict) else (str(item), "")
        body = clean(text) or (" · ".join(p["facts"]) + ".")
        nxt = clean(nxt).rstrip(".")
        out += [f"■ {p['title']}", body + (f"\n→ 이어서 볼 것: {nxt}" if nxt else ""), ""]
    return "\n".join(out).strip()


def gpt_comment(briefing: dict) -> str:
    """주간 총평 = 시장 분위기 한두 문장 + 이번 주 짚을 점 3~5개(2026-11-02 사용자 결정 - 목록을 다시 읽어 주는 총평은 의미가 없다).
    짚을 점은 코드가 고르고(겹침·엇갈림·관찰 노트·매크로↔테마), GPT는 그 사실을 이유 짐작 없이 문장으로만 잇는다."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return ""

    import requests

    from src.llm.openai_json import build_payload, model_for

    market = comment_facts(briefing).get("시장") or {}
    points = comment_points(briefing)
    briefing["_comment_points"] = points   # 미리 보기 출력용(저장 전에 지운다)
    # 화면용 관련 기사 - 소제목(■ 줄)과 같은 글자로 묶는다. GPT를 거치지 않은 원문 제목·링크
    briefing["comment_news"] = {p["title"]: p["news"] for p in points if p.get("news")}
    briefing["comment_points"] = [p["title"] for p in points]   # 텔레그램 '짚을 점' 제목 줄
    if not market and not points:
        return ""
    for_gpt = [{"제목": p["title"], "왜 골랐나": p["note"], "사실": p["facts"],
                **({"같은 주 관련 기사 제목(참고)": [n["title"] for n in p["news"]]} if p.get("news") else {})} for p in points]
    label_meaning = {LABEL_KO_SHORT[k]: v for k, v in LABEL_MEANING.items()}
    prompt = f"""개인 투자 리서치 도구의 주간 브리핑입니다. 화면에는 목록이 이미 다 있으니, 목록을 다시 읽어 주지 말고 아래 '짚을 점'만 풀어 주세요.

시장(지난 1주, 크기는 말로 바꿔 둠):
{json.dumps(market, ensure_ascii=False)}

짚을 점(코드가 여러 칸에서 겹치거나 엇갈리는 사실을 골라 둠):
{json.dumps(for_gpt, ensure_ascii=False, indent=1)}

테마 라벨 뜻: {json.dumps(label_meaning, ensure_ascii=False)}

JSON으로만 답하세요: {{"market": "...", "points": [{{"body": "...", "next": "..."}}, ...]}}
- market: 시장 분위기 한두 문장. '시장 환경(정해진 조합)'에 이름이 있으면 그 이름을 그대로 쓰되(바꾸거나 새 이름을 만들지 말 것) 사실 문구를 옮겨 적지 말고 문장 안에 자연스럽게 넣는다(예: "미국과 한국 모두 변동성과 신용 스프레드가 함께 오르는 '위험 회피' 흐름이 이어졌다"). 두 시장 조합이 같으면 한 번만. 지수·금리·환율·수급 중 서로 엇갈리거나 같은 방향인 것을 짚기.
- points: 짚을 점과 같은 순서·같은 개수.
  body: 두세 문장. 그 점의 사실들이 서로 어떻게 맞물리는지 - 같은 방향인지, 엇갈리는지, 내 기대(관찰 노트)와 맞았는지.
    라벨은 이름만 대지 말고 뜻을 풀어서. 소속 종목이 있으면 이름을 들어서.
    사실에 관찰 노트가 있으면 4주 전 기대가 맞았는지 빗나갔는지를 반드시 한 문장 넣으세요(어느 시장의 노트인지도).
  next: 이어서 확인할 것 한 가지. "~할지", "~하는지"로 끝나는 짧은 구절. 주어(테마·종목 이름)를 넣어서 따로 읽어도 뜻이 통하게.
    그 점의 사실에서 나온 것이어야 하고 점마다 달라야 합니다.

문체 - 경제 신문의 시황·종목 기사처럼:
- 기사체 평서문 "~했다", "~이다", "~모습이다"로 끝냅니다("~습니다" 쓰지 않음). 추측은 "~로 보인다" 정도만.
- 첫 문장에 요점을 먼저(두괄식). 그다음 관련 사실 두세 개는 "~했고", "~한 반면", "~하면서", "~과 달리", "한편" 같은 연결어로 엮는다.
  짧은 과거형 문장을 끊어서 나열하지 않는다("맞았다. 조용했다. 올랐다."처럼 읽으면 어색하다 - 11/7 사용자).
- 문장 끝을 다양하게: "~로 돌아섰다", "~가 이어졌다", "~이 붙었다", "~에 이름을 올렸다", "~에서 빠졌다", "~가 예정돼 있다" 등.
  같은 끝맺음("~했다", "~였다", "~맞았다")을 두 문장 연달아 쓰지 않는다.
- 실적 이야기에는 '실적'을 꼭 넣는다("조선은 오름세로 돌아섰다"만 쓰면 주가 얘기로 읽힌다 → "조선은 소속 기업 실적이 오름으로 돌아섰다").
- 한 문장에 주어를 둘 겹치지 않는다("가나테마가 실적이 …" 대신 "가나테마는 실적이 …").
- "엇갈린 신호를 보였다", "흐름을 보였다" 대신 "엇갈렸다", "올랐다"처럼 바로 쓴다.
- 기사 언급을 문단마다 "관련 기사에서는 ~ 보도가 있었다"로 똑같이 끝내지 않는다. 필요한 문단에서만, 꼴을 바꿔 한 구절로.
- "이는 ~"으로 앞 문장을 받지 말고 사실을 바로 쓴다. "불안감·심리" 같은 해석 말도 쓰지 않는다(지표가 어떻게 움직였는지만).
- 관찰 노트는 "'뉴스가 늘 것'이라고 적어 둔 기대가 맞았다/빗나갔다"처럼 결과를 분명히. "기대가 유지되었다"처럼 맞았는지 흐려지는 말은 쓰지 않는다.
- 피동·번역투를 쓰지 않습니다: "분류됐다"·"분류되었다" 대신 "라벨이 붙었다", "나타났다"는 되도록 피하고 무엇이 어떻게 됐는지 바로.
  "~의 경우", "~에 있어서", "~를 보였다", "~세를 보였다"는 쓰지 않습니다.
- 문단을 소제목 이름으로 시작하지 마세요(제목이 이미 위에 있음). "좋은 신호와 주의할 신호" 같은 설명문 대신 무엇과 무엇이 엇갈렸는지 직접.
- 문체 예시(가상의 이름, 사실 아님 - 말투만 참고하고 내용은 절대 옮기지 마세요):
  나쁜 예: "가나테마 테마에서는 한국의 실적이 크게 좋아졌지만 뉴스와 주가는 조용해 '숨은 강세'로 분류되었습니다."
  좋은 예: "실적이 먼저 움직였다. 한국 가나테마는 이익이 크게 늘었지만 뉴스와 주가는 아직 조용해 '숨은 강세' 라벨이 붙었다."
  나쁜 예: "다라전자는 관심도가 상승했지만 영업이익이 크게 줄어들었습니다. 좋은 신호와 주의할 신호가 함께 나타났습니다."
  좋은 예: "관심과 실적이 거꾸로 갔다. 다라전자는 관심도가 '높음'까지 올랐지만 잠정 영업이익은 전년보다 크게 줄었다."
  next 예: "가나테마 주가가 실적을 따라 오를지", "다라전자 관심도가 다음 주에도 이어질지"

- 관련 기사 제목은 참고만: 어떤 주제의 보도가 이어졌는지 한 구절로 덧붙일 수 있습니다(예: "수출 확대 관련 보도도 이어졌다").
  기사 제목을 따옴표째 옮기지 말고 무엇을 다룬 기사인지 짧은 우리말로(영어 제목도 우리말로), 제목 속 숫자·전망·원인 해석·매수 권유는 쓰지 마세요.
  기사는 화면에 링크로 따로 붙습니다.
- 제목은 쓰지 마세요(코드가 붙입니다). 늘고 줄어든 것은 사실에 적힌 크기(크게·소폭)를 그대로 살리고, 좋다·나쁘다로 바꾸지 마세요.
- 사실에 없는 원인·효과·전망은 쓰지 마세요("영향", "때문", "덕분", "힘입어", "~로 인한", "이로 인해", "긍정적", "부정적" 금지 - 이런 말이 든 문장은 코드가 통째로 지운다).
  "이는 ~을 시사한다/보여준다/의미한다" 같은 해석 맺음 문장도 쓰지 마세요.
- 숫자(%·금액·건수)는 쓰지 마세요. 이름은 적힌 글자 그대로. 매수·매도 권유 금지."""

    titles = [n["title"] for p in points for n in (p.get("news") or [])]
    best, best_key = "", None
    for attempt in range(2):   # 같은 끝맺음이 이어지거나 기사 제목을 그대로 옮기면 한 번 더 받아 나은 쪽(11/7 월간 보고서에서 옮김)
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=build_payload(model_for("briefing_comment"),
                                   "당신은 경제 신문 증권부 기자입니다. 주어진 사실만으로 자연스럽게 읽히는 기사체 문장을 쓰고, 사실 사이의 관계를 짚습니다.",
                                   prompt, max_output_tokens=2000, temperature=0.4),
                timeout=90,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            _LAST_RAW_COMMENT[0] = raw   # 미리 보기에서 뒷손질 전후를 비교하려고
            data = json.loads(raw)
            text = assemble_comment(str(data.get("market") or ""), list(data.get("points") or []), points)
        except Exception as e:
            logger.warning("GPT 총평 생성 실패: %s", type(e).__name__)
            continue
        rep, vt = repeat_endings(text), verbatim_titles(text, titles)
        vague = vague_reviews(points, list(data.get("points") or []))
        logger.info("총평 %d차: 같은 끝맺음 연속 %d곳, 기사 제목 그대로 %d곳, 회고 결과가 흐린 문단 %d곳", attempt + 1, rep, vt, vague)
        k = (-vague, -vt, -rep)
        if best_key is None or k > best_key:
            best, best_key = text, k
        if vague == 0 and vt == 0 and rep <= 1:
            break
    return best


def vague_reviews(points: list[dict], bodies: list) -> int:
    """관찰 노트 회고가 든 짚을 점인데 본문에 '맞았다/빗나갔다'가 없는 문단 수 - 11/7 미리 보기
    "뉴스 증가를 기대한 것과는 다르게 전개되었다"처럼 결과가 흐려졌다."""
    n = 0
    for i, p in enumerate(points):
        if not any("관찰 노트" in f for f in p.get("facts") or []):
            continue
        item = bodies[i] if i < len(bodies) else ""
        body = str(item.get("body") or "") if isinstance(item, dict) else str(item)
        if not re.search(r"맞았|빗나갔|판단(하지|할 수) 못|판단할 데이터", body):
            n += 1
    return n


def repeat_endings(text: str) -> int:
    """앞 문장과 끝맺음(마지막 세 글자)이 같은 문장 수 - ■ 소제목 줄·'→ 이어서 볼 것' 줄은 빼고 문단마다."""
    n = 0
    for para in text.split("\n"):
        if not para.strip() or para.startswith(("■", "→")):
            continue
        ends = [x.strip()[-4:-1] for x in re.split(r"(?<=다\.)\s+", para.strip()) if x.strip()]
        n += sum(1 for a, b in zip(ends, ends[1:]) if a == b)
    return n


def verbatim_titles(text: str, titles: list[str]) -> int:
    """기사 제목을 통째로 옮긴 곳 수(제목 앞 열두 글자가 그대로 들어 있으면)."""
    return sum(1 for t in titles if len(t) >= 12 and t[:12] in text)


# ── 텔레그램 요약 ────────────────────────────────────────────────────────────

MY_TG_MAX = 8
MY_TAGS = ("my", "note")


def my_stocks_week(b: dict, mine: dict[str, list[str]], names: dict[str, str]) -> dict:
    """브리핑 맨 위 "관심 종목에 생긴 일"(2026-10-21, 사용자 결정 B) - 내 관심·관찰 노트 종목에 이번 주 생긴 일을 한 칸에.
    새로 계산하지 않고 이미 만든 칸(실적 발표·한국 공시·8-K·내부자 매수·실적 반전·노트 회고)에서 그 종목 줄만 모은다.
    mine: '시장:종목' -> ['my'|'note']. 순서: 내 관심 먼저 → 생긴 일 수 → 종목. 점수 없음(원칙 1)."""
    ev: dict[str, list[dict]] = {}

    def add(key: str, kind: str, text: str, anchor: str, date: str | None = None, warn: bool = False) -> None:
        if key in mine:
            ev.setdefault(key, []).append({"kind": kind, "text": text, "anchor": anchor, "date": date, "warn": warn})

    for x in (b.get("earnings_week") or {}).get("items", []):
        add(f"{x['market']}:{x['symbol']}", "실적 발표", f"{_md(x['date'])}{' 예상' if x.get('estimate') else ''}", "earnings", x["date"])
    kd = b.get("kr_disclosures") or {}
    for k in ("contract", "termination", "amend", "prelim"):
        for x in (kd.get(k) or {}).get("items", []):
            add(f"KR:{x['symbol']}", "한국 공시", x["summary"], "disclosures", x["date"], k == "termination")
    for x in (b.get("us_8k_week") or {}).get("items", []):
        add(f"US:{x['symbol']}", "8-K", ", ".join(i["label"] for i in x["items"]), "us8k", x["date"], x.get("warn", False))
    ins = b.get("insider_week") or {}
    for g in (ins.get("items") or []) + (ins.get("discovery") or []):
        who = g["roles"][0] if g["buyers"] == 1 else f"{g['buyers']}명"
        add(f"{g['market']}:{g['symbol']}", "내부자 매수", f"{who} {fmt_money(g['value'], g['market'])}", "insider", g.get("last_date"))
    inst_ko = {"new": "신규 매수", "added": "추가 매수", "reduced": "일부 매도", "sold": "전량 매도"}
    for x in (b.get("inst_13f_week") or {}).get("tagged", []):
        add(f"US:{x['ticker']}", "13F", f"{x['manager'].split(' (')[0]} {inst_ko.get(x['status'], x['status'])}", "inst13f",
            None, x["status"] in ("sold", "reduced"))
    for x in (b.get("turnaround") or {}).get("added", []):
        yoy = f" {x['yoy'] * 100:+.0f}%" if x.get("yoy") is not None else ""
        add(f"{x['market']}:{x['symbol']}", "실적 반전", f"새로 들어옴 ({x['basis']}{yoy})", "turnaround")
    for rv in b.get("observation_reviews") or []:
        if rv.get("kind") == "stock" and rv.get("ticker"):
            add(f"{rv.get('market')}:{rv['ticker']}", "노트 회고", f"{rv.get('checkpoint') or ''} 회고 도착".strip(), "notes")
    items = []
    for key, events in ev.items():
        market, symbol = key.split(":", 1)
        items.append({"market": market, "symbol": symbol, "name": names.get(key), "tags": mine[key], "events": events})
    items.sort(key=lambda x: ("my" not in x["tags"], -len(x["events"]), x["symbol"]))
    return {"watched": len(mine), "count": len(items), "items": items}


def get_my_stocks_week(b: dict) -> dict | None:
    tags, names = interest_tags_names()
    mine = {k: [t for t in v if t in MY_TAGS] for k, v in tags.items() if any(t in MY_TAGS for t in v)}
    return my_stocks_week(b, mine, names) if mine else None


def _quarter(period: str) -> str:
    return f"{period[:4]} Q{(int(period[5:7]) - 1) // 3 + 1}" if period and len(period) >= 7 else period


def build_telegram_summary(b: dict) -> str:
    """텔레그램 요약 본문. 숫자는 전부 DB·시세에서 온 값만 쓴다 - GPT 총평은 웹에만 둔다(원칙 2)."""
    def disp(item):
        flag = MARKET_FLAG.get(item["market"], "")
        label = (item.get("name") or item["symbol"]) if item["market"] == "KR" else item["symbol"]
        # parse_mode=HTML이라 이름의 &·<·>를 이스케이프해야 한다 - 안 하면 F&F 같은 종목 하나로
        # 텔레그램이 "can't parse entities"를 내고 메시지 전체가 안 간다(2026-10-05 리뷰).
        return f"{flag} {html.escape(label)}"

    lines = [f"<b>📋 Undercurrent Sonar 주간 브리핑</b> · {_md(b['week'])}", ""]

    # 묶음 머리 - 웹 브리핑과 같은 순서·이름(2026-11-02, 사용자 결정: 시장 → 종목 변화 → 테마 → 일정 → 공시)
    def group(title: str) -> None:
        lines.extend(["", f"━━ {title} ━━"])

    # 맨 위: 내 관심·노트 종목에 생긴 일(2026-10-21) - 아래 칸들에서 그 종목 줄만 모은 것
    my = b.get("my_stocks_week")
    if my and my.get("count"):
        lines.append(f"<b>⭐ 관심 종목에 생긴 일</b> {my['count']}종목")
        for x in my["items"][:MY_TG_MAX]:
            evs = " · ".join(("⚠️" if e["warn"] else "") + f"{e['kind']} {html.escape(e['text'])}" for e in x["events"])
            lines.append(f"  {disp(x)} {evs}")
        if my["count"] > MY_TG_MAX:
            lines.append(f"  외 {my['count'] - MY_TG_MAX}종목")
        lines.append("")

    # 총평 '이번 주 짚을 점' 제목(2026-11-05) - 코드가 만든 제목만(GPT 문장은 웹에만, 원칙 2). 본문·기사는 웹 링크로
    pts = b.get("comment_points") or []
    if pts:
        group("🔎 이번 주 짚을 점")
        lines += [f"  • {html.escape(t)}" for t in pts[:5]]

    group("🌐 시장")
    idx = []
    if b["us"].get("index_chg_1w") is not None:
        idx.append(f"🇺🇸 SPY {b['us']['index_chg_1w']:+.1f}%")
    if b["kr"].get("index_chg_1w") is not None:
        kospi = f"🇰🇷 KOSPI {b['kr']['index_chg_1w']:+.1f}%"
        # 외국인 순매수(5거래일 합) - 지표 줄을 늘리지 않고 지수 옆에 붙인다(2026-10-17)
        fk = ((b.get("kr_flows") or {}).get("KOSPI") or {}).get("foreign")
        if fk is not None:
            kospi += f" (외국인 {fmt_krw_flow(fk)})"
        idx.append(kospi)
    vx = (b.get("macro") or {}).get("vix") or {}
    if idx and vx.get("value") is not None:   # VIX는 지수 옆에(2026-11-05) - 지표 줄을 늘리지 않는다
        idx.append(f"VIX {vx['value']:.1f}" + (f" ({vx['chg_1w']:+.1f})" if vx.get("chg_1w") is not None else ""))
    if idx:
        lines.append("지난 1주 " + " · ".join(idx))

    # 금리·환율 - 지수 옆에 같이 본다. 값·변화 모두 macro_snapshot에서 온 숫자 그대로.
    mc = b.get("macro") or {}
    rates = []
    r = mc.get("us10y") or {}
    if r.get("value") is not None:
        chg = f" ({r['chg_1w']:+.2f}%p)" if r.get("chg_1w") is not None else ""
        rates.append(f"미 10년물 {r['value']:.2f}%{chg}")
    kr = mc.get("kr3y") or {}
    if kr.get("value") is not None:
        chg = f" ({kr['chg_1w']:+.2f}%p)" if kr.get("chg_1w") is not None else ""
        rates.append(f"국고채 3년 {kr['value']:.2f}%{chg}")
    fx = mc.get("usdkrw") or {}
    if fx.get("value") is not None:
        chg = f" ({fx['chg_1w']:+,.0f}원)" if fx.get("chg_1w") is not None else ""
        rates.append(f"원/달러 {fx['value']:,.0f}원{chg}")
    dx = mc.get("dxy") or {}
    if dx.get("value") is not None:
        chg = f" ({dx['chg_1w']:+.1f})" if dx.get("chg_1w") is not None else ""
        rates.append(f"달러인덱스 {dx['value']:.1f}{chg}")
    oil = mc.get("wti") or {}
    if oil.get("value") is not None:
        rates.append(f"WTI ${oil['value']:.1f}{_pct_chg(oil)}")
    if rates:
        label = "금리·환율·유가" if oil.get("value") is not None else "금리·환율"
        lines.append(f"{label} " + " · ".join(rates))

    group("🔖 종목 변화")
    wl = b["watchlist"]
    lines.append("")
    if wl["has_prev"]:
        lines.append(f"<b>🔖 워치리스트</b> {wl['total']}종목 · 신규 {wl['added_count']} · 탈락 {wl['removed_count']}")
        for a in wl["added"][:3]:
            lines.append(f"  + {disp(a)}")
        if wl["added_count"] > 3:
            lines.append(f"  외 {wl['added_count'] - 3}개")
    else:
        lines.append(f"<b>🔖 워치리스트</b> {wl['total']}종목")

    ta = b.get("turnaround")
    if ta:
        counts = " · ".join(f"{MARKET_FLAG.get(m, m)} {n}" for m, n in sorted(ta["by_market"].items(), reverse=True))
        lines.append("")
        head = f"<b>🔄 실적 반전</b> {counts or '0'}"
        if ta["has_prev"]:
            head += f" · 신규 {ta['added_count']} · 빠짐 {ta['removed_count']}"
        lines.append(head)
        for a in ta["added"][:3]:
            yoy = f" {a['basis']} {a['yoy'] * 100:+.0f}%" if a.get("yoy") is not None else ""
            lines.append(f"  + {disp(a)}{yoy}")
        if ta["added_count"] > 3:
            lines.append(f"  외 {ta['added_count'] - 3}개")
        if not ta["has_prev"]:
            lines.append("  (새로 들어온 종목 비교는 다음 주부터)")

    if b["sentiment_heating"]:
        lines.append("")
        lines.append("<b>📈 관심도 상승</b>")
        for h in b["sentiment_heating"][:3]:
            lines.append(f"  {disp(h)} {h['path']}")

    group("📡 테마")
    # 테마 레이더 - 이 툴의 중심이라 라벨이 없어도 상태를 한 줄은 쓴다
    tl = b.get("theme_labels") or {}
    counts = tl.get("label_counts") or {}
    lines.append("")
    lines.append(f"<b>📡 테마 레이더</b> ({_md(tl.get('week_start'))} 주)")
    if not counts:
        lines.append("  테마 신호 데이터 없음")
    elif not any(counts.values()):
        lines.append("  아직 라벨 없음 - 뉴스 기준선(4주)이 쌓이면 붙습니다")
    else:
        lines.append("  라벨 " + " · ".join(f"{MARKET_FLAG[m]} {n}개" for m, n in counts.items()))
        names = load_theme_names()
        for t in tl.get("new_labels", [])[:5]:
            lines.append(f"  + {MARKET_FLAG.get(t.get('market', 'US'), '')} "
                         f"{html.escape(names.get(t['theme_id'], t['theme_id']))} — {label_display(t['label'])}")
        if len(tl.get("new_labels", [])) > 5:
            lines.append(f"  외 {len(tl['new_labels']) - 5}개")

    group("📅 이번 주 일정")
    ew = b.get("earnings_week")
    if ew and ew.get("total"):
        counts = " · ".join(f"{MARKET_FLAG.get(m, m)} {n}" for m, n in sorted(ew["by_market"].items(), reverse=True))
        lines.append("")
        lines.append(f"<b>📅 이번 주 실적 발표</b> {counts}")
        # 내 관심·관찰 노트·실적 반전 종목을 먼저 - 없으면 날짜 빠른 순
        shown = [x for x in ew["items"] if x.get("tags")] or ew["items"]
        for x in shown[:EARNINGS_TG_MAX]:
            tag = " · ".join(EARNINGS_TAG_KO.get(t, t) for t in x.get("tags") or [])
            lines.append(f"  {_md(x['date'])}{'(예상)' if x.get('estimate') else ''} {disp(x)}" + (f" · {tag}" if tag else ""))
        if ew["total"] > min(len(shown), EARNINGS_TG_MAX):
            lines.append(f"  외 {ew['total'] - min(len(shown), EARNINGS_TG_MAX)}개")

    group("📄 공시 · 내부자")
    kd = b.get("kr_disclosures")
    kinds = ("contract", "prelim", "termination", "amend")
    if kd and any((kd.get(k) or {}).get("count") for k in kinds):
        lines.append("")
        extra = "".join(f" · {name} {kd[k]['count']}" for k, name in (("termination", "계약 해지"), ("amend", "금액 정정"))
                        if (kd.get(k) or {}).get("count"))
        lines.append(f"<b>📝 한국 공시</b> 지난 7일 공급계약 {kd['contract']['count']} · 잠정실적 {kd['prelim']['count']}{extra}")
        # 관심 표시 붙은 공시 먼저, 그다음 계약 해지(드물고 중요), 남는 칸은 매출 대비 큰 공급계약
        tagged = [x for k in kinds for x in (kd.get(k) or {}).get("items", []) if x["tags"]]
        rest = [x for x in (kd.get("termination") or {}).get("items", []) if not x["tags"]] + \
               [x for x in kd["contract"]["items"] if not x["tags"]]
        for x in (tagged + rest)[:DISC_TG_MAX]:
            tag = " · ".join(DISC_TAG_KO.get(t, t) for t in x["tags"])
            lines.append(f"  {_md(x['date'])} {disp({'market': 'KR', 'symbol': x['symbol'], 'name': x['name']})} "
                         f"{html.escape(x['summary'])}" + (f" · {tag}" if tag else ""))

    ins = b.get("insider_week")
    if ins and ins.get("total"):
        counts = " · ".join(f"{MARKET_FLAG.get(m, m)} {n}" for m, n in sorted(ins["by_market"].items(), reverse=True))
        lines.append("")
        lines.append(f"<b>🧑‍💼 내부자 장내 매수</b> 지난 7일 {counts}종목")

        def ins_line(g: dict, extra: str) -> str:
            who = g["roles"][0] if g["buyers"] == 1 else f"{g['buyers']}명"
            plan = " (계획 매수)" if g["all_plan"] else ""
            return f"  {disp(g)} {html.escape(who)} {fmt_money(g['value'], g['market'])}{plan}" + (f" · {extra}" if extra else "")
        for g in ins["items"][:INSIDER_TG_MAX]:
            lines.append(ins_line(g, " · ".join(DISC_TAG_KO.get(t, t) for t in g["tags"])))
        disc = ins.get("discovery") or []
        if disc:
            lines.append(f"  🆕 새로 발견(관심 외) {ins.get('discovery_count', len(disc))}종목")
            for g in disc[:INSIDER_DISC_TG_MAX]:
                lines.append(ins_line(g, FIN_KO.get((g.get("finance") or {}).get("status"), "재무 미확인")))

    u8 = b.get("us_8k_week")
    if u8 and u8.get("total"):
        kinds = " · ".join(f"{k} {n}" for k, n in list(u8["by_kind"].items())[:4])
        lines.append("")
        lines.append(f"<b>🇺🇸 미국 주요 공시(8-K)</b> 지난 7일 {u8['total']}건 - {kinds}")
        for x in u8["items"][:US8K_TG_MAX]:
            tag = " · ".join(DISC_TAG_KO.get(t, t) for t in x["tags"])
            labels = ", ".join(("⚠️" if i["warn"] else "") + i["label"] for i in x["items"])
            lines.append(f"  {_md(x['date'])} {disp(x)} {html.escape(labels)}" + (f" · {tag}" if tag else ""))
        if u8["total"] > US8K_TG_MAX:
            lines.append(f"  외 {u8['total'] - US8K_TG_MAX}건")

    inst = b.get("inst_13f_week")
    if inst and inst.get("filers"):
        lines.append("")
        lines.append(f"<b>🏦 유명 투자자 13F</b> 이번 주 신고 {inst['filers']}곳 · 분기 말 보유(45일 늦음)")
        for it in inst["items"][:INST_TG_MANAGERS]:
            nm = lambda x: html.escape(x.get("ticker") or (x.get("issuer") or "?"))  # noqa: E731
            parts = []
            if it["new"]:
                parts.append("신규 " + ", ".join(nm(x) for x in it["new"][:INST_TG_NAMES]) + (f" 외 {it['counts']['new'] - INST_TG_NAMES}" if it["counts"]["new"] > INST_TG_NAMES else ""))
            if it["sold"]:
                parts.append("전량 매도 " + ", ".join(nm(x) for x in it["sold"][:INST_TG_NAMES]) + (f" 외 {it['counts']['sold'] - INST_TG_NAMES}" if it["counts"]["sold"] > INST_TG_NAMES else ""))
            lines.append(f"  {html.escape(it['name'])} ({_quarter(it['period'])}): " + (" · ".join(parts) if parts else "신규 매수·전량 매도 종목 없음"))
        if inst["filers"] > INST_TG_MANAGERS:
            lines.append(f"  외 {inst['filers'] - INST_TG_MANAGERS}곳")
        lines.append(f'  <a href="{SITE_URL}/investors">전체 보기</a>')

    reviews = b.get("observation_reviews") or []
    if reviews:
        names = load_theme_names()
        lines.append("")
        lines.append(f"<b>🔁 관찰 노트 회고 도착</b> {len(reviews)}건")
        for rv in reviews[:3]:
            target = (names.get(rv.get("theme_id") or "", rv.get("theme_id") or "") if rv.get("kind") == "theme"
                      else rv.get("ticker") or "")
            res = rv.get("expect_results") or {}
            facts = ", ".join(
                f"{EXPECT_KO.get(rv.get('kind'), {}).get(k, k)} "
                f"{'판단 불가' if v is None else '일어남' if v else '안 일어남'}" for k, v in res.items())
            lines.append(f"  {MARKET_FLAG.get(rv.get('market'), '')} {html.escape(target)} "
                         f"{rv.get('checkpoint')}주 전" + (f" · {facts}" if facts else ""))
        lines.append(f'  <a href="{SITE_URL}/notes">판단 남기기</a>')

    lines += ["", f'<a href="{SITE_URL}/briefing">전체 브리핑 보기</a>']
    # 묶음 머리 정리: 머리 바로 뒤 빈 줄은 빼고(머리와 첫 칸이 한 덩어리로 - 메시지를 나눌 때도 같이 간다),
    # 안에 아무 줄도 없는 묶음(다음 줄이 또 머리이거나 끝)은 머리째 뺀다
    out: list[str] = []
    for i, l in enumerate(lines):
        if l.startswith("━━"):
            nxt = next((x for x in lines[i + 1:] if x), "")
            if not nxt or nxt.startswith("━━") or nxt.startswith("<a href"):
                continue
        if not l and out and out[-1].startswith("━━"):
            continue
        out.append(l)
    # 지수·금리 줄이 다 비면 빈 줄이 겹친다 - 연속 빈 줄은 하나로
    return "\n".join(l for i, l in enumerate(out) if l or (i > 0 and out[i - 1]))


TELEGRAM_MAX = 3900   # 텔레그램 한 메시지 4,096자 - 여유를 둔다


def split_telegram(text: str, limit: int = TELEGRAM_MAX) -> list[str]:
    """칸(빈 줄로 나뉜 블록) 단위로 limit 안에 들어가게 나눈다. 한 칸이 limit보다 길면 줄 단위로.
    태그(<b>…</b>)는 줄마다 닫혀 있어 줄·칸 경계에서 잘라도 깨지지 않는다(2026-10-21 - 칸이 늘어 길이 초과 위험)."""
    blocks = text.split("\n\n")
    parts: list[str] = []
    cur = ""
    for blk in blocks:
        pieces = [blk] if len(blk) <= limit else blk.split("\n")
        for piece in pieces:
            sep = "\n\n" if piece is blk else "\n"
            if cur and len(cur) + len(sep) + len(piece) > limit:
                parts.append(cur)
                cur = piece[:limit]
            else:
                cur = f"{cur}{sep}{piece}" if cur else piece[:limit]
    if cur:
        parts.append(cur)
    return parts


def send_telegram_summary(b: dict) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        logger.info("텔레그램 미설정 — 발송 건너뜀")
        return

    parts = split_telegram(build_telegram_summary(b))
    for i, text in enumerate(parts, 1):
        body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                           "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body, headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
            logger.info("텔레그램 주간 요약 발송 완료 (%d/%d, %d자)", i, len(parts), len(text))
        except Exception as e:
            logger.error("텔레그램 발송 실패 (%d/%d): %s", i, len(parts), e)


def print_dry_run(b: dict, points: list | None) -> None:
    """--dry-run 출력 - 칸마다 건수·몇 줄, 총평, 텔레그램 본문. 저장하지 않는다."""
    def n(v):
        return len(v) if isinstance(v, (list, dict)) else ("-" if v is None else v)
    print(f"== 브리핑 미리 보기 (week={b['week']}, 저장·발송 안 함) ==")
    for k in ("us", "kr", "macro", "kr_flows", "kr_disclosures", "insider_week", "us_8k_week", "inst_13f_week",
              "sentiment_heating", "observation_reviews", "earnings_week", "my_stocks_week"):
        v = b.get(k)
        print(f"  {k}: {type(v).__name__} {n(v)}" + (f" keys={list(v)[:8]}" if isinstance(v, dict) else ""))
    for mk, st in (b.get("regime") or {}).items():
        print(f"  regime {mk} {st.get('week')}: " + (", ".join(c["name"] for c in st.get("combos") or []) or "조합 없음"))
    w = b.get("watchlist") or {}
    print(f"  watchlist: 후보 {w.get('total')} · 신규 {w.get('added_count')} · 탈락 {w.get('removed_count')} (직전 스냅샷 {'있음' if w.get('has_prev') else '없음'})")
    for x in (w.get("added") or [])[:10]:
        print(f"    + {x.get('market')}:{x.get('symbol')} {x.get('name') or ''}")
    for x in (w.get("removed") or [])[:10]:
        print(f"    - {x.get('market')}:{x.get('symbol')} {x.get('name') or ''}")
    t = b.get("turnaround") or {}
    print(f"  turnaround: {t.get('total')} · 신규 {t.get('added_count')} · 빠짐 {t.get('removed_count')}")
    tl = b.get("theme_labels") or {}
    print(f"  theme_labels: 신규 {len(tl.get('new_labels') or [])} · 소멸 {len(tl.get('dropped_labels') or [])} · 기준 주 {tl.get('week')}")
    print("\n== 짚을 점(코드가 고름) ==")
    for pt in points or []:
        print(f"[{pt['kind']}] {pt['title']}\n  - " + "\n  - ".join(pt["facts"]))
    print("\n== 총평 ==\n" + (b.get("gpt_comment") or "(없음)"))
    print("\n== 텔레그램 ==\n" + build_telegram_summary(b))


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-telegram", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="지금 데이터로 브리핑 전체를 만들어 요약·총평·텔레그램 본문만 출력(저장·스냅샷·발송 없음, 2026-11-05)")
    parser.add_argument("--preview-comment", action="store_true",
                        help="저장된 최근 브리핑으로 총평만 만들어 출력(저장·발송 안 함, 2026-11-02)")
    args = parser.parse_args()

    if args.preview_comment:
        rows = _payload(turso_exec("SELECT week, payload FROM weekly_briefings ORDER BY week DESC LIMIT 1"))
        if not rows:
            logger.info("저장된 브리핑 없음")
            return
        b = rows[0]["_data"]
        if not b.get("my_stocks_week"):
            b["my_stocks_week"] = get_my_stocks_week(b)
        # 저장된 브리핑보다 나중에 생긴 매크로 칸(VIX·장단기 금리차, 2026-11-05)은 지금 값으로 채워 미리 보기(저장은 안 함)
        fresh = get_macro_week() or {}
        if b.get("macro") is not None:
            for k in ("vix", "spread_10y_2y"):
                if k not in b["macro"] and fresh.get(k):
                    b["macro"][k] = fresh[k]
        final = gpt_comment(b)
        print("== 짚을 점(코드가 고름) ==")
        for pt in b.pop("_comment_points", None) or []:
            print(f"[{pt['kind']}] {pt['title']}\n  - " + "\n  - ".join(pt["facts"]))
            for n in pt.get("news") or []:
                print(f"    📰 {n['published_at']} {n['source']} | {n['title']}")
        if _LAST_RAW_COMMENT[0] and _LAST_RAW_COMMENT[0] != final:
            print("\n== GPT 원문(뒷손질 전) ==\n" + _LAST_RAW_COMMENT[0])
        print(f"\n== 총평 ({b.get('week')}) ==\n" + (final or "(생성 실패 또는 OPENAI_API_KEY 없음)"))
        if final:
            b["gpt_comment"] = final
        if b.get("comment_news"):   # 웹 미리 보기용(짧다)
            print("\n== COMMENT_NEWS ==\n" + json.dumps(b["comment_news"], ensure_ascii=False))
        if os.environ.get("PREVIEW_TELEGRAM"):
            print("\n== 텔레그램(지금 코드의 순서) ==\n" + build_telegram_summary(b))
        # 웹 화면 미리 보기용 - 새 총평을 넣은 브리핑 한 주치(사이트 /api/briefing이 주는 것과 같은 내용). 저장은 하지 않는다.
        import base64
        import gzip
        if os.environ.get("PREVIEW_PAYLOAD"):   # 로그가 길어져서 필요할 때만
            print("\n== PAYLOAD_B64 ==\n" + base64.b64encode(gzip.compress(json.dumps(b, ensure_ascii=False).encode())).decode())
        return

    DRY_RUN[0] = args.dry_run
    now = datetime.now(timezone.utc)
    # 브리핑 주차 라벨 = 다가오는 월요일 (일요일 밤 실행 기준)
    days_to_mon = (7 - now.weekday()) % 7
    week = (now + timedelta(days=days_to_mon)).strftime("%Y-%m-%d")

    logger.info("주간 브리핑 생성 시작 (week=%s)", week)

    briefing = {
        "week": week,
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "us": get_market_week("US"),
        "kr": get_market_week("KR"),
        "macro": get_macro_week(),
        "kr_flows": get_kr_flows_week(),
        "regime": get_regime_week(),
        "watchlist": get_watchlist_changes(),
        "turnaround": get_turnaround_changes(week),
        "earnings_week": get_earnings_week(week),
        "kr_disclosures": get_kr_disclosures_week(),
        "insider_week": get_insider_week(),
        "us_8k_week": get_us_8k_week(),
        "inst_13f_week": get_inst_13f_week(),
        "sentiment_heating": get_sentiment_week(week),
        "theme_labels": get_theme_label_changes(),
        "observation_reviews": get_observation_reviews(),
    }
    briefing["my_stocks_week"] = get_my_stocks_week(briefing)
    briefing["gpt_comment"] = gpt_comment(briefing)   # 관심 종목 칸까지 만든 뒤 - 총평이 그 내용도 쓴다(2026-11-02)
    points = briefing.pop("_comment_points", None)

    if args.dry_run:
        print_dry_run(briefing, points)
        return

    turso_exec(
        "CREATE TABLE IF NOT EXISTS weekly_briefings ("
        "  week TEXT PRIMARY KEY, payload TEXT NOT NULL,"
        "  created_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    turso_exec(
        "INSERT INTO weekly_briefings (week, payload) VALUES (?, ?) "
        "ON CONFLICT(week) DO UPDATE SET payload=excluded.payload, created_at=datetime('now')",
        [week, json.dumps(briefing, ensure_ascii=False)],
    )
    logger.info("저장 완료 — 워치리스트 신규 %d·탈락 %d, 관심도 상승 %d, 테마 라벨 신규 %d·소멸 %d",
                briefing["watchlist"]["added_count"], briefing["watchlist"]["removed_count"],
                len(briefing["sentiment_heating"]),
                len(briefing["theme_labels"]["new_labels"]), len(briefing["theme_labels"]["dropped_labels"]))

    if not args.no_telegram:
        send_telegram_summary(briefing)


if __name__ == "__main__":
    main()
