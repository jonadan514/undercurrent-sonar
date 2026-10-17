"""pykrx로 코스피·코스닥 투자자별 순매수 금액(일별)을 받아 JSON으로 떨어뜨린다 (2026-10-17).

주간 브리핑에 한국 시장 수급(외국인·기관·개인 순매수)을 넣기 위한 것(BACKLOG_briefing_indicators C).
국고채(fetch_kr_treasury_pykrx.py)와 같은 이유로 격리 환경(pandas<3.0 + pykrx 1.2.8)에서 돌고 저장소 모듈을 import하지 않는다.
저장은 scripts/save_kr_investor_flows.py가 한다. 금액 단위는 원(KRX 값 그대로).

    /tmp/krxenv/bin/python scripts/fetch_kr_investor_flows_pykrx.py --out data/kr_investor_flows.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

MARKETS = ("KOSPI", "KOSDAQ")
INVESTORS = {"foreign": "외국인", "institution": "기관", "individual": "개인"}   # 열 이름에 이 글자가 들어간 열
LOOKBACK_DAYS = 21


def _log(msg: str) -> None:
    print(f"[kr-flows] {msg}", flush=True)


def pick_columns(columns) -> dict[str, str]:
    """KRX 열 이름(외국인합계·기관합계·개인 등) -> 우리 키. 못 찾은 투자자는 빠진다."""
    out = {}
    for key, word in INVESTORS.items():
        col = next((c for c in columns if word in str(c) and "기타" not in str(c)), None)
        if col is not None:
            out[key] = col
    return out


def fetch() -> list[dict]:
    from pykrx import stock
    end = datetime.utcnow() + timedelta(hours=9)          # KST
    start = end - timedelta(days=LOOKBACK_DAYS)
    rows: list[dict] = []
    for market in MARKETS:
        try:
            df = stock.get_market_trading_value_by_date(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), market)
        except Exception as e:  # noqa: BLE001
            _log(f"{market} 조회 실패 {type(e).__name__}: {str(e)[:120]}")
            continue
        if df is None or df.empty:
            _log(f"{market} 빈 응답")
            continue
        cols = pick_columns(df.columns)
        _log(f"{market} {len(df)}거래일, 열 {list(df.columns)} -> {cols}")
        for idx, r in df.iterrows():
            day = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
            for key, col in cols.items():
                try:
                    rows.append({"date": day, "market": market, "investor": key, "value": float(r[col])})
                except (TypeError, ValueError):
                    pass
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/kr_investor_flows.json")
    args = ap.parse_args()
    rows = fetch()
    if not rows:
        _log("받은 값이 없음 - 파일을 쓰지 않는다")
        return 1
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"fetched_at": datetime.utcnow().isoformat(), "rows": rows}, f, ensure_ascii=False, indent=1)
    last = max(r["date"] for r in rows)
    for r in rows:
        if r["date"] == last:
            _log(f"{last} {r['market']} {r['investor']} {r['value'] / 1e8:,.0f}억")
    return 0


if __name__ == "__main__":
    sys.exit(main())
