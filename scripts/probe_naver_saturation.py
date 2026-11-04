"""네이버 뉴스 상한 실측 - 읽기 전용(DB에 쓰지 않는다, 2026-11-04).

한국 뉴스 축은 키워드당 최신순 약 1100건까지만 읽을 수 있어(start 상한 1000) 기사가 많은 주를 다 못 센다.
키워드마다 넘길 수 있는 데까지 받아 "그만큼이 며칠치인가"를 재서, 실제 하루·한 주 기사량이 상한을 얼마나 넘는지 낸다.
total(네이버가 주는 전체 검색 결과 수)도 남긴다 - 며칠 간격 두 번 재면 그 차이가 실제 증가량으로 쓸 만한지 볼 수 있다.

사용법: python scripts/probe_naver_saturation.py [--themes k_beauty petrochemical]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from collectors.theme_news_collector import NAVER_DISPLAY, NAVER_ENDPOINT, NAVER_MAX_START, naver_credentials  # noqa: E402

# 지금 수집기가 한 주 창 안에서 셀 수 있는 최대치 근처. 이보다 많은 주간 기사량이면 그 키워드는 상한에 눌린다.
WEEK_CAP = NAVER_MAX_START + NAVER_DISPLAY


def probe_keyword(keyword: str, headers: dict) -> dict:
    stamps, total, start = [], None, 1
    while start <= NAVER_MAX_START:
        resp = requests.get(NAVER_ENDPOINT, headers=headers, timeout=15,
                            params={"query": keyword, "display": NAVER_DISPLAY, "start": start, "sort": "date"})
        resp.raise_for_status()
        payload = resp.json()
        total = payload.get("total") if total is None else total
        items = payload.get("items") or []
        for item in items:
            try:
                stamps.append(parsedate_to_datetime(item.get("pubDate") or ""))
            except (ValueError, TypeError):
                pass
        if len(items) < NAVER_DISPLAY:
            break
        start += NAVER_DISPLAY
        time.sleep(0.2)
    if len(stamps) < 2:
        return {"keyword": keyword, "fetched": len(stamps), "total": total, "span_days": None, "per_day": None, "est_week": None}
    span_days = (max(stamps) - min(stamps)).total_seconds() / 86400
    per_day = len(stamps) / span_days if span_days > 0 else None
    return {"keyword": keyword, "fetched": len(stamps), "total": total, "span_days": round(span_days, 2),
            "per_day": round(per_day, 1) if per_day else None, "est_week": round(per_day * 7) if per_day else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--themes", nargs="*", default=None)
    args = ap.parse_args()
    creds = naver_credentials()
    if not creds:
        print("NAVER 키 없음", flush=True)
        return 1
    headers = {"X-Naver-Client-Id": creds[0], "X-Naver-Client-Secret": creds[1]}
    themes = [t for t in yaml.safe_load((ROOT / "config" / "themes.yaml").read_text(encoding="utf-8"))["themes"]
              if t.get("status") == "active" and "KR" in t.get("markets", []) and t.get("keywords_ko")]
    if args.themes:
        themes = [t for t in themes if t["id"] in set(args.themes)]

    rows = []
    for t in themes:
        for kw in t["keywords_ko"]:
            try:
                r = probe_keyword(kw, headers)
            except Exception as e:  # noqa: BLE001 - 시험이라 한 키워드 실패로 멈추지 않는다
                print(f"[probe] {t['id']} {kw}: 실패 {type(e).__name__}", flush=True)
                continue
            r["theme_id"] = t["id"]
            rows.append(r)
            print(f"[probe] {t['id']:22s} {kw}: 읽음 {r['fetched']} / {r['span_days']}일치 / 하루 {r['per_day']} / 주 추정 {r['est_week']} / total {r['total']}", flush=True)

    est = [r["est_week"] for r in rows if r["est_week"] is not None]
    over = [r for r in rows if (r["est_week"] or 0) > WEEK_CAP]
    print(f"[probe] 키워드 {len(rows)}개, 주 추정 중앙값 {statistics.median(est) if est else None}, 최대 {max(est) if est else None}", flush=True)
    print(f"[probe] 주 {WEEK_CAP}건 넘는 키워드 {len(over)}개 = 지금 방식으로 다 못 세는 키워드", flush=True)
    days = [r["per_day"] for r in rows if r["per_day"]]
    if days:
        print(f"[probe] 하루 기사량 최대 {max(days)} - 이게 {WEEK_CAP}보다 작으면 매일 수집으로 전부 셀 수 있다", flush=True)
    by_theme = {}
    for r in over:
        by_theme.setdefault(r["theme_id"], []).append(r["keyword"])
    print(f"[probe] 상한 키워드가 있는 테마 {len(by_theme)}/{len(themes)}: {json.dumps(by_theme, ensure_ascii=False)}", flush=True)
    Path("out").mkdir(exist_ok=True)
    Path("out/naver_probe.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
