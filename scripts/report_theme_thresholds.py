"""테마 레이더 기준값 점검 보고서 (읽기 전용, 2026-10-25).

마스터 계획 8장 "테마 임계값(themes.yaml config): 임의값. 수 주 운영 후 조정"의 근거 자료.
기준값을 바꾸지 않는다 - 지금 기준에서 화살표·라벨이 얼마나 자주 붙는지, 매주 뒤집히는지, 기준선 근처에 몰려
있는지만 보여 준다. 바꿀지는 사용자가 보고 정한다. 트랩 필터 기준값은 대상이 아니다.

본다:
  1. 축별 화살표 분포(up2·up1·flat·down·na) - 시장별
  2. 원값 분포(뉴스 배수·실적 개선 비율·주가 초과수익) 분위수와 기준값 위치
  3. 기준선 근처(±10% 폭) 비율 - 여기 몰리면 작은 변동에도 화살표가 바뀐다
  4. 주간 뒤집힘 - 같은 테마의 화살표가 지난주와 다른 비율(뉴스·주가. 실적은 분기 자료라 제외)
  5. 라벨 분포·주당 라벨 붙은 테마 수·라벨 지속 주 수
  6. 늘 na인 테마, 한 번도 라벨이 안 붙은 테마
백필 주(news_backfilled=1)는 SPEC §2.4대로 참고용이라 따로 센다.

    python scripts/report_theme_thresholds.py [--weeks 12]
"""
from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.db.data_store import get_db  # noqa: E402

THEMES_YAML = ROOT / "config" / "themes.yaml"
ARROWS = ("up2", "up1", "flat", "down", "na")
COLS = ("theme_id", "market", "week_start", "news_count", "news_ratio", "news_arrow", "news_backfilled",
        "earn_ratio", "earn_arrow", "price_excess", "price_arrow", "label", "member_count")


def quantiles(vals: list[float]) -> str:
    if len(vals) < 5:
        return f"n={len(vals)} (분위수 계산하기엔 적음)"
    v = sorted(vals)
    q = lambda p: v[min(len(v) - 1, int(round(p * (len(v) - 1))))]  # noqa: E731
    return (f"n={len(v)} · 최소 {v[0]:.2f} · 10% {q(.1):.2f} · 25% {q(.25):.2f} · 중앙 {q(.5):.2f} · "
            f"75% {q(.75):.2f} · 90% {q(.9):.2f} · 최대 {v[-1]:.2f}")


def near_share(vals: list[float], cuts: dict[str, float], width: float, rel: bool = False) -> str:
    """기준값 ±width 안에 든 비율. rel이면 기준값의 비율(뉴스 배수 ±10%), 아니면 절대 폭."""
    if not vals:
        return "-"
    parts = []
    for k, c in cuts.items():
        n = sum(1 for x in vals if abs(x - c) <= (width * abs(c) if rel else width))
        parts.append(f"{k} {c:g} 근처 {n}/{len(vals)} ({n / len(vals) * 100:.0f}%)")
    return " · ".join(parts)


def arrow_dist(rows: list[dict], key: str) -> str:
    c = Counter((r[key] or "na") for r in rows)
    tot = sum(c.values()) or 1
    return " · ".join(f"{a} {c.get(a, 0)} ({c.get(a, 0) / tot * 100:.0f}%)" for a in ARROWS)


def flip_rate(rows: list[dict], key: str) -> tuple[int, int, list[tuple[str, int, int]]]:
    """같은 테마 연속 두 주(7일 차이) 중 화살표가 다른 비율. na가 낀 쌍은 뺀다. -> (뒤집힘, 비교 쌍, 테마별 상위)"""
    by_theme: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_theme[r["theme_id"]].append(r)
    flips = pairs = 0
    per: list[tuple[str, int, int]] = []
    for tid, rs in by_theme.items():
        rs.sort(key=lambda r: r["week_start"])
        f = p = 0
        for a, b in zip(rs, rs[1:]):
            x, y = a[key] or "na", b[key] or "na"
            # 빠진 주(예: 09-07)를 건너뛴 두 줄은 연속 주가 아니다
            if "na" in (x, y) or (date.fromisoformat(b["week_start"]) - date.fromisoformat(a["week_start"])).days != 7:
                continue
            p += 1
            f += x != y
        flips += f
        pairs += p
        if p:
            per.append((tid, f, p))
    per.sort(key=lambda t: (-t[1] / t[2], -t[2]))
    return flips, pairs, per


def label_runs(rows: list[dict]) -> list[int]:
    """같은 라벨이 연속으로 붙은 주 수 목록."""
    by_theme: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_theme[r["theme_id"]].append(r)
    runs: list[int] = []
    for rs in by_theme.values():
        rs.sort(key=lambda r: r["week_start"])
        cur, n = None, 0
        for r in rs:
            if r["label"] and r["label"] == cur:
                n += 1
            else:
                if cur:
                    runs.append(n)
                cur, n = r["label"], 1 if r["label"] else 0
        if cur:
            runs.append(n)
    return runs


def _num(v):
    """Turso가 숫자를 글자로 돌려줄 때가 있다 - 비교 전에 숫자로."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _norm(r: dict) -> dict:
    for k in ("news_count", "news_ratio", "earn_ratio", "price_excess", "member_count"):
        r[k] = _num(r[k])
    r["news_backfilled"] = bool(_num(r["news_backfilled"]))
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=12, help="최근 몇 주를 볼지")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(THEMES_YAML, encoding="utf-8"))
    conf = cfg["config"]
    names = {t["id"]: t["name_ko"] for t in cfg["themes"]}
    nt, et, pt = conf["news_thresholds"], conf["earnings_thresholds"], conf["price_thresholds"]
    min_articles = conf.get("default_min_articles", 10)

    conn = get_db()
    # 세 축이 다 계산된 주(주가 축이 있는 주)만 본다 - 그 전 주들은 뉴스만 백필한 줄이라 실적·주가가 늘 비어 분포가 흐려진다
    weeks = [r[0] for r in conn.execute(
        "SELECT DISTINCT week_start FROM theme_signals WHERE price_arrow IS NOT NULL ORDER BY week_start DESC LIMIT ?",
        (args.weeks,)).fetchall()]
    if not weeks:
        print("세 축이 계산된 주가 없음")
        return 1
    rows = [_norm(dict(zip(COLS, r))) for r in conn.execute(
        f"SELECT {', '.join(COLS)} FROM theme_signals WHERE week_start >= ? AND week_start <= ? AND price_arrow IS NOT NULL "
        "ORDER BY market, theme_id, week_start", (min(weeks), max(weeks))).fetchall()]
    news_only = conn.execute("SELECT COUNT(DISTINCT week_start), MIN(week_start) FROM theme_signals WHERE price_arrow IS NULL").fetchone()

    print(f"# 테마 레이더 기준값 점검 ({min(weeks)} ~ {max(weeks)}, 세 축이 계산된 최근 {len(weeks)}주)\n")
    if news_only and news_only[0]:
        print(f"(뉴스만 백필된 주 {news_only[0]}개({news_only[1]}~)는 실적·주가가 없어 뺐다)\n")
    print("기준값(themes.yaml config, 바꾸지 않음):")
    print(f"- 뉴스 배수(이번 주 / 직전 8주 중앙값): ↑↑ {nt['strong_up']} · ↑ {nt['up']} · ↓ {nt['down']}, 기사 {min_articles}건 미만은 na")
    print(f"- 실적(매출 성장 개선 기업 비율): ↑↑ {et['strong_up']} · ↑ {et['up']} · ↓ {et['down']}")
    print(f"- 주가(소속 4주 수익률 중앙값 - 지수, 소수): ↑↑ {pt['strong_up']} · ↑ {pt['up']} · ↓ {pt['down']}\n")

    for market in ("US", "KR"):
        mr = [r for r in rows if r["market"] == market]
        if not mr:
            continue
        live = [r for r in mr if not r["news_backfilled"]]
        themes = sorted({r["theme_id"] for r in mr})
        print(f"## {market} - 테마 {len(themes)}개 · 테마-주 {len(mr)}줄 (백필 주 {len(mr) - len(live)}줄 포함)\n")

        print("### 1. 화살표 분포")
        for key, label in (("news_arrow", "뉴스"), ("earn_arrow", "실적"), ("price_arrow", "주가")):
            print(f"- {label}: {arrow_dist(mr, key)}")
        few = sum(1 for r in mr if r["news_count"] is not None and r["news_count"] < min_articles)
        print(f"- 뉴스 기사 {min_articles}건 미만(na 사유): {few}/{len(mr)}줄")
        print()

        print("### 2. 원값 분포와 기준값 위치")
        nr = [float(r["news_ratio"]) for r in mr if r["news_ratio"] is not None]
        er = [float(r["earn_ratio"]) for r in mr if r["earn_ratio"] is not None]
        px = [float(r["price_excess"]) for r in mr if r["price_excess"] is not None]
        print(f"- 뉴스 배수: {quantiles(nr)}")
        print(f"- 실적 개선 비율: {quantiles(er)}")
        print(f"- 주가 초과수익: {quantiles(px)}")
        print()

        print("### 3. 기준선 근처")
        print(f"- 뉴스(기준값 ±10%): {near_share(nr, {'↑↑': nt['strong_up'], '↑': nt['up'], '↓': nt['down']}, 0.1, rel=True)}")
        print(f"- 실적(±0.03): {near_share(er, {'↑↑': et['strong_up'], '↑': et['up'], '↓': et['down']}, 0.03)}")
        print(f"- 주가(±1%p): {near_share(px, {'↑↑': pt['strong_up'], '↑': pt['up'], '↓': pt['down']}, 0.01)}")
        print()

        print("### 4. 주간 뒤집힘 (지난주와 화살표가 다른 비율, na 낀 주 제외)")
        for key, label in (("news_arrow", "뉴스"), ("price_arrow", "주가")):
            f, p, per = flip_rate(mr, key)
            print(f"- {label}: {f}/{p} ({f / p * 100:.0f}%)" if p else f"- {label}: 비교할 연속 주 없음")
            top = [f"{names.get(t, t)} {a}/{b}" for t, a, b in per[:5] if a]
            if top:
                print(f"  - 자주 바뀐 테마: {', '.join(top)}")
        print()

        print("### 5. 라벨")
        lc = Counter(r["label"] for r in mr if r["label"])
        print(f"- 라벨 붙은 줄 {sum(lc.values())}/{len(mr)} · " + (" · ".join(f"{k} {v}" for k, v in lc.most_common()) or "없음"))
        per_week = Counter(r["week_start"] for r in mr if r["label"])
        print("- 주별 라벨 붙은 테마 수: " + " · ".join(f"{w[5:]} {per_week.get(w, 0)}" for w in sorted(weeks)))
        runs = label_runs(mr)
        if runs:
            print(f"- 같은 라벨 연속 주 수: 중앙 {statistics.median(runs):g}주 · 1주로 끝난 것 {sum(1 for x in runs if x == 1)}/{len(runs)}")
        na_label = sum(1 for r in mr if any((r[k] or "na") == "na" for k in ("news_arrow", "earn_arrow", "price_arrow")))
        print(f"- 축 하나라도 na라 라벨 판정 못 한 줄: {na_label}/{len(mr)}")
        print()

        print("### 6. 늘 비어 있는 테마")
        by_t: dict[str, list[dict]] = defaultdict(list)
        for r in mr:
            by_t[r["theme_id"]].append(r)
        for key, label in (("news_arrow", "뉴스"), ("earn_arrow", "실적"), ("price_arrow", "주가")):
            always = [names.get(t, t) for t, rs in by_t.items() if all((r[key] or "na") == "na" for r in rs)]
            print(f"- {label} 늘 na: {len(always)}개" + (f" - {', '.join(always)}" if always else ""))
        never = [names.get(t, t) for t, rs in by_t.items() if not any(r["label"] for r in rs)]
        print(f"- 라벨 한 번도 없음: {len(never)}/{len(by_t)}개")
        small = sorted({(names.get(t, t), int(rs[-1]["member_count"])) for t, rs in by_t.items()
                        if rs[-1]["member_count"] is not None and rs[-1]["member_count"] < 5}, key=lambda x: x[1])
        if small:
            print(f"- 소속 5종목 미만(실적·주가 na가 정상): {', '.join(f'{n} {c}' for n, c in small)}")
        print()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
