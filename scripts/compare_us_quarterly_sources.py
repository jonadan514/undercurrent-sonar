"""미국 분기 재무 출처 비교(읽기 전용, 2026-11-05 사용자 결정 - 수집 경로 정리 1단계).

지금 미국 실적 축(compute_theme_earnings)과 워치리스트 분기 영업이익률·분기 매출(compute_watchlist_valuation)은
재무 캐시(fundamentals_cache income_quarterly, 토요일 백필 - yfinance)를 읽는다. 같은 회사의 분기 숫자가
quarterly_financials_raw(미국 유니버스 yfinance + 워치리스트 SEC 공시)에도 따로 쌓이고, PSR·PER·분기 리서치는 그쪽을 읽는다.
한국은 11/2에 "공시 원본(DART) 먼저, 최신 분기가 늦은 쪽"으로 맞췄다(theme_earnings.pick_revenue).

미국도 같은 규칙으로 바꾸면 무엇이 달라지는지 먼저 본다 - 아무것도 쓰지 않는다:
  1) 출처별로 매출을 확보한 종목 수, 고른 출처, 최신 분기가 어느 쪽이 늦은지
  2) 기준 성장률(미국 유니버스 중앙값)이 어떻게 바뀌는지 - 캐시는 테마·워치리스트 종목만 분기가 있어 표본이 작다
  3) 테마별 실적 축 화살표: 지금(캐시) vs 바꾼 뒤(공시 원본 우선)
  4) 두 출처가 같은 분기를 가진 종목의 전년 같은 분기 대비 성장률 차이
  5) 워치리스트 미국 후보의 분기 영업이익률 판정(개선/유지/악화) 일치 여부

    python scripts/compare_us_quarterly_sources.py
    python scripts/compare_us_quarterly_sources.py --market KR   # 워치리스트 한국 후보만(5번) - 실적 축은 11/2부터 이미 DART 먼저

2026-11-05 한국 워치리스트도 같은 비교(사용자: 다음 작업 2번). 한국은 공시 원본 표가 DART(연결 우선)다.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.db.data_store import get_db
from src.db.fundamentals_cache import get_cached_financials_bulk
from src.db.quarterly_financials import quarters_to_income_df, select_quarters_bulk
from src.db.theme_signals import get_approved_theme_members
from analyzers.theme_earnings import (compute_earn_signal, dart_revenue_series, pick_revenue,
                                      reference_growth_for_market, yoy_growth)
from analyzers.company_growth import quarterly_margin_change, quarterly_revenue_yoy
from collectors.watchlist_collector import get_us_universe

THEMES_YAML = ROOT / "config" / "themes.yaml"
DIFF_PP = 0.02   # 같은 분기인데 성장률이 2%p 넘게 다르면 따로 센다


def _log(msg: str) -> None:
    print(msg, flush=True)


def _cache_series(data: dict | None) -> pd.Series | None:
    """compute_theme_earnings와 같은 방식 - 캐시 분기 손익의 Total Revenue 행."""
    if not data:
        return None
    q = data.get("financials_quarterly")
    if q is None or q.empty or "Total Revenue" not in q.index:
        return None
    s = q.loc["Total Revenue"].dropna()
    return s if len(s) else None


def _q(s: pd.Series | None) -> str | None:
    return None if s is None or not len(s) else str(pd.Timestamp(s.index[0]).to_period("Q"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["US", "KR"], default="US")
    args = ap.parse_args()
    if args.market == "KR":
        conn = get_db()
        watchlist_section(conn, "KR")
        conn.close()
        return 0

    data = yaml.safe_load(THEMES_YAML.read_text(encoding="utf-8"))
    themes = [t for t in data["themes"] if t.get("status") == "active" and "US" in (t.get("markets") or [])]
    thresholds = data.get("config", {}).get("earnings_thresholds", {"strong_up": 0.70, "up": 0.55, "down": 0.45})
    conn = get_db()

    members = {}
    for t in themes:
        ms = get_approved_theme_members(conn, t["id"], "US", ("direct", "partial"))
        if ms:
            members[t["id"]] = ms
    member_tickers = {m["ticker"] for ms in members.values() for m in ms}
    universe = [it["symbol"] for it in get_us_universe()]
    needed = sorted(member_tickers | set(universe))
    _log(f"미국 테마 {len(members)}개, 소속 {len(member_tickers)}종목, 유니버스 {len(universe)}종목")

    cache = get_cached_financials_bulk(conn, needed)
    raw = select_quarters_bulk(conn, needed, "US")
    cache_rev = {t: _cache_series(cache.get(t)) for t in needed}
    raw_rev = {t: dart_revenue_series(raw.get(t, [])) for t in needed}
    new_rev, src = {}, {}
    for t in needed:
        new_rev[t], src[t] = pick_revenue(cache_rev[t], raw_rev[t])

    def usable(s):
        return yoy_growth(s) is not None

    for label, group in (("소속 기업", sorted(member_tickers)), ("유니버스", universe)):
        c = sum(1 for t in group if usable(cache_rev[t]))
        r = sum(1 for t in group if usable(raw_rev[t]))
        n = sum(1 for t in group if usable(new_rev[t]))
        _log(f"\n[1] {label} {len(group)}종목 - 성장률 계산 가능: 지금(캐시) {c} → 바꾼 뒤 {n}  (공시 원본 표만 {r})")
    chosen = {"DART": 0, "yfinance": 0, None: 0}
    newer = {"raw": 0, "cache": 0, "same": 0}
    for t in member_tickers:
        chosen[src[t]] += 1
        a, b = _q(cache_rev[t]), _q(raw_rev[t])
        if a and b:
            newer["same" if a == b else "raw" if b > a else "cache"] += 1
    _log(f"    소속 기업이 고른 출처: 공시 원본 표 {chosen['DART']} · 캐시 {chosen['yfinance']} · 없음 {chosen[None]}")
    _log(f"    둘 다 있는 소속 기업의 최신 분기: 같음 {newer['same']} · 공시 원본이 늦음 {newer['raw']} · 캐시가 늦음 {newer['cache']}")
    sec = sum(1 for t in member_tickers for r in raw.get(t, [])[:1] if (r.get("source") or "").lower().startswith("sec"))
    _log(f"    소속 기업 중 최신 분기가 SEC 공시인 곳 {sec}")

    ref_old = reference_growth_for_market({t: cache_rev[t] for t in universe}, "US")
    ref_new = reference_growth_for_market({t: new_rev[t] for t in universe}, "US")
    fmt = lambda v: "표본 부족" if v is None else f"{v * 100:+.1f}%"  # noqa: E731
    _log(f"\n[2] 기준 성장률(미국 유니버스 중앙값): 지금 {fmt(ref_old)} (표본 {sum(1 for t in universe if usable(cache_rev[t]))}) → "
         f"바꾼 뒤 {fmt(ref_new)} (표본 {sum(1 for t in universe if usable(new_rev[t]))})")

    _log("\n[3] 테마별 실적 축 (지금 → 바꾼 뒤)   개선/유효(부족) 비율 화살표")
    changed = 0
    for tid, ms in sorted(members.items()):
        o = compute_earn_signal(ms, cache_rev, thresholds, ref_old)
        n = compute_earn_signal(ms, new_rev, thresholds, ref_new)
        mark = "  " if o["arrow"] == n["arrow"] else "▶ "
        changed += o["arrow"] != n["arrow"]
        r = lambda x: "-" if x["ratio"] is None else f"{x['ratio']:.2f}"  # noqa: E731
        _log(f"  {mark}{tid:<24} {o['improved']}/{o['members'] - o['insufficient']}({o['insufficient']}) {r(o)} {o['arrow']:<4} → "
             f"{n['improved']}/{n['members'] - n['insufficient']}({n['insufficient']}) {r(n)} {n['arrow']:<4}  as_of {o['as_of']} → {n['as_of']}")
    _log(f"  화살표가 바뀌는 테마 {changed}/{len(members)}")

    diffs = []
    for t in member_tickers:
        a, b = cache_rev[t], raw_rev[t]
        if usable(a) and usable(b) and _q(a) == _q(b):
            d = yoy_growth(b) - yoy_growth(a)
            diffs.append((abs(d), t, yoy_growth(a), yoy_growth(b)))
    big = sorted([x for x in diffs if x[0] > DIFF_PP], reverse=True)
    _log(f"\n[4] 같은 분기를 가진 소속 기업 {len(diffs)}곳 중 성장률이 {DIFF_PP * 100:.0f}%p 넘게 다른 곳 {len(big)}"
         + (f", 차이 중앙값 {statistics.median(x[0] for x in diffs) * 100:.2f}%p" if diffs else ""))
    for d, t, a, b in big[:12]:
        _log(f"    {t:<6} 캐시 {a * 100:+.1f}% / 공시 원본 표 {b * 100:+.1f}%  (최신 출처 {raw.get(t, [{}])[0].get('source')})")

    watchlist_section(conn, "US")
    conn.close()
    return 0


def watchlist_section(conn, market: str) -> None:
    """[5] 워치리스트 후보의 분기 영업이익률 판정·분기 매출 YoY - 재무 캐시 vs 공시 원본 표(같은 분기 판정 비교 포함)."""
    from analyzers.company_growth import pick_latest
    cands = [r[0] for r in conn.execute("SELECT symbol FROM watchlist_candidates WHERE market = ?", (market,)).fetchall()]
    names = dict(conn.execute("SELECT symbol, name FROM watchlist_candidates WHERE market = ?", (market,)).fetchall())
    wl_cache = get_cached_financials_bulk(conn, cands)
    wl_raw = select_quarters_bulk(conn, cands, market)
    agree = disagree = only_old = only_new = 0
    same_q_diff, newer, examples = 0, {"raw": 0, "cache": 0, "same": 0}, []
    final_change = 0
    for t in cands:
        q_old = (wl_cache.get(t) or {}).get("financials_quarterly")
        q_new = quarters_to_income_df(wl_raw.get(t, []))
        a, b = quarterly_margin_change(q_old), quarterly_margin_change(q_new)
        picked = pick_latest(b, a)   # 실제로 바꾸면 쓰일 값(최신 분기가 늦은 쪽, 같으면 원본)
        if (picked or {}).get("status") != (a or {}).get("status"):
            final_change += 1
        if a and b:
            newer["same" if a["quarter"] == b["quarter"] else "raw" if b["quarter"] > a["quarter"] else "cache"] += 1
            if a["status"] == b["status"]:
                agree += 1
            else:
                disagree += 1
                same_q_diff += a["quarter"] == b["quarter"]
                examples.append(f"{t} {names.get(t) or ''} {a['quarter']} {a['status']}({a['now'] * 100:.1f}%) → "
                                f"{b['quarter']} {b['status']}({b['now'] * 100:.1f}%)")
        elif a:
            only_old += 1
        elif b:
            only_new += 1
    label = "미국" if market == "US" else "한국"
    _log(f"\n[5] 워치리스트 {label} 후보 {len(cands)}종목 분기 영업이익률 판정: 같음 {agree} · 다름 {disagree}(같은 분기인데 다름 {same_q_diff}) · "
         f"지금만 있음 {only_old} · 바꾼 뒤만 있음 {only_new}")
    _log(f"    둘 다 있는 종목의 최신 분기: 같음 {newer['same']} · 공시 원본이 늦음 {newer['raw']} · 캐시가 늦음 {newer['cache']}")
    _log(f"    실제로 바꾸면(늦은 쪽, 같으면 원본) 판정이 달라지는 종목 {final_change}")
    for e in examples[:15]:
        _log(f"    {e}")
    ry_old = sum(1 for t in cands if quarterly_revenue_yoy((wl_cache.get(t) or {}).get("financials_quarterly")))
    ry_new = sum(1 for t in cands if quarterly_revenue_yoy(quarters_to_income_df(wl_raw.get(t, []))))
    _log(f"    분기 매출 전년 대비 계산 가능: 지금 {ry_old} → 바꾼 뒤(원본만) {ry_new}")


if __name__ == "__main__":
    raise SystemExit(main())
