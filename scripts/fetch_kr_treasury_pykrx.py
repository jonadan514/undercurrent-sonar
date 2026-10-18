"""pykrx로 국고채 금리(장외 최종호가 수익률)를 받아 JSON으로 떨어뜨린다 (2026-10-05).

주간 브리핑의 금리·환율 줄에 한국 금리를 넣기 위한 것. 한국은행 ECOS 키 없이 이미 쓰는 pykrx(KRX)로 받는다.
fetch_kr_universe_pykrx.py와 같은 이유로 격리 환경(pandas<3.0 + pykrx 1.2.8)에서 돌고 저장소 모듈을 import하지 않는다.
저장은 scripts/save_kr_treasury.py가 JSON을 읽어 한다.

    /tmp/krxenv/bin/python scripts/fetch_kr_treasury_pykrx.py --out data/kr_treasury.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

TENORS = {"kr3y": "국고채 3년", "kr10y": "국고채 10년"}
LOOKBACK_DAYS = 21   # 달력일 - 5거래일 전 비교에 넉넉하게


def _log(msg: str) -> None:
    print(f"[kr-treasury] {msg}", flush=True)


def _norm(name: str) -> str:
    return str(name).replace(" ", "")


MAX_CONSECUTIVE_FAILS = 10   # 연속 실패면 KRX가 막은 것 - 더 두드리지 않고 멈춘다(2026-10-17: 1년 채우기 중 차단)


def fetch(lookback_days: int = LOOKBACK_DAYS, skip_days: int = 0, sleep_sec: float = 0.0) -> dict:
    import time
    from pykrx import bond
    out: dict[str, list[dict]] = {k: [] for k in TENORS}
    end = datetime.utcnow() + timedelta(hours=9)          # KST
    day = end - timedelta(days=skip_days)                 # 이미 채운 최근 구간은 건너뛴다(빈 구간만 채우기)
    seen = fails = 0
    # 날짜별 스냅샷(그날의 전 만기 수익률)으로 받는다 - 기간 조회 형식은 버전마다 인자가 달라서.
    while (end - day).days <= lookback_days:
        if day.weekday() < 5:
            ymd = day.strftime("%Y%m%d")
            try:
                df = bond.get_otc_treasury_yields(ymd)
            except Exception as e:  # noqa: BLE001
                _log(f"{ymd} 조회 실패 {type(e).__name__}: {str(e)[:120]}")
                df = None
            if sleep_sec:
                time.sleep(sleep_sec)
            if df is None or df.empty:
                fails += 1
                if fails >= MAX_CONSECUTIVE_FAILS:
                    _log(f"{MAX_CONSECUTIVE_FAILS}일 연속 실패 - KRX 차단으로 보고 멈춘다({ymd}까지 조회)")
                    break
            else:
                fails = 0
                col = "수익률" if "수익률" in df.columns else df.columns[0]
                idx = {_norm(i): i for i in df.index}
                for key, name in TENORS.items():
                    src = idx.get(_norm(name))
                    if src is not None:
                        try:
                            out[key].append({"date": day.strftime("%Y-%m-%d"), "value": float(df.loc[src, col])})
                        except (TypeError, ValueError):
                            pass
                seen += 1
        day -= timedelta(days=1)
    _log(f"조회한 평일 {seen}일 - " + ", ".join(f"{k} {len(v)}개" for k, v in out.items()))
    return drop_holiday_repeats(out)


def drop_holiday_repeats(data: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """휴장일(추석·한글날 등)에 KRX가 직전 거래일 값을 그 날짜로 다시 주는 경우를 걸러낸다.
    모든 만기 값이 바로 앞(이전 날짜) 거래일과 똑같은 날은 같은 호가의 반복으로 보고 뺀다 - 그대로 두면
    "5거래일 전 대비"가 하루씩 밀린다(2026-10-05 리뷰: 21일 동안 16일이 들어왔는데 실제 거래일은 약 14일)."""
    dates = sorted({r["date"] for v in data.values() for r in v})
    by_key = {k: {r["date"]: r["value"] for r in v} for k, v in data.items()}
    keep, prev = set(), None
    for d in dates:
        cur = tuple(by_key[k].get(d) for k in data)
        if prev is not None and cur == prev:
            continue
        keep.add(d)
        prev = cur
    dropped = len(dates) - len(keep)
    if dropped:
        _log(f"휴장일 반복 값 {dropped}일 제외")
    return {k: [r for r in v if r["date"] in keep] for k, v in data.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/kr_treasury.json")
    # 개요 1년 그래프용 처음 채우기(2026-10-17) - 하루씩 조회라 1년이면 수 분 걸린다
    ap.add_argument("--lookback-days", type=int, default=LOOKBACK_DAYS)
    ap.add_argument("--skip-days", type=int, default=0, help="최근 며칠(달력일)은 건너뛴다 - 빈 옛 구간만 채울 때")
    ap.add_argument("--sleep", type=float, default=0.0, help="조회 사이 쉬는 초 - 긴 채우기에서 차단 피하기")
    args = ap.parse_args()
    data = fetch(args.lookback_days, args.skip_days, args.sleep)
    if not any(data.values()):
        _log("받은 값이 없음 - 파일을 쓰지 않는다")
        return 1
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"fetched_at": datetime.utcnow().isoformat(), "items": data}, f, ensure_ascii=False, indent=1)
    for k, v in data.items():
        if v:
            _log(f"{k} 최근 {v[0]['date']} {v[0]['value']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
