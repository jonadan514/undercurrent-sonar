"""시장 환경(레짐) 축 미리 보기 - 읽기 전용(2026-11-05, 레짐 모듈 1단계).

저장된 일별 지표(macro_history·kr_rates·kr_investor_flows)로 지난 WEEKS주의 매주 금요일 시점 축 상태(수준·방향)와 조합 이름을
다시 계산해 보여 준다. 아무것도 쓰지 않는다. 기준값(상·하위 20%, 4주, 평소 변화폭 1배)과 조합을 정하기 전에 실제로 어떻게
나오는지 보려는 것 - 마지막에 더 긴 기간에서 조합 이름이 몇 주에 한 번 붙는지도 센다.

    python scripts/report_market_regime.py
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.analyzers import regime as rg
from src.db.data_store import get_db

WEEKS = 12
FREQ_WEEKS = 40


def load_series(conn) -> dict[str, list[tuple[str, float]]]:
    out: dict[str, list[tuple[str, float]]] = {}
    for d, k, v in conn.execute("SELECT date, key, value FROM macro_history").fetchall():
        out.setdefault(k, []).append((str(d), float(v)))
    try:
        for d, k, v in conn.execute("SELECT date, key, value FROM kr_rates WHERE value IS NOT NULL").fetchall():
            out.setdefault(k, []).append((str(d), float(v)))
    except Exception as e:  # noqa: BLE001
        print(f"kr_rates 없음 {type(e).__name__}")
    try:
        for d, v in conn.execute("SELECT date, value FROM kr_investor_flows WHERE market = 'KOSPI' AND investor = 'foreign' "
                                 "AND value IS NOT NULL").fetchall():
            out.setdefault("kospi_foreign", []).append((str(d), float(v)))
    except Exception as e:  # noqa: BLE001
        print(f"kr_investor_flows 없음 {type(e).__name__}")
    return out


def fridays(last: date, n: int) -> list[str]:
    f = last - timedelta(days=(last.weekday() - 4) % 7)
    return [(f - timedelta(weeks=i)).isoformat() for i in reversed(range(n))]


def fmt_val(key: str, v: float | None) -> str:
    if v is None:
        return "-"
    if key == "kospi_foreign":
        return f"{v / 1e12:+.1f}조"
    if key in ("usdkrw",):
        return f"{v:,.0f}"
    return f"{v:.2f}"


def main() -> int:
    conn = get_db()
    s = load_series(conn)
    conn.close()
    print("== 지표별 표본 ==")
    for k in sorted({k for m in rg.AXES.values() for _, _, k in m} | {k for v in rg.CONTEXT.values() for k in v}):
        pts = sorted(s.get(k) or [])
        print(f"  {rg.LABEL_KO.get(k, k):<28} {len(pts):>4}일  {pts[0][0] if pts else '-'} ~ {pts[-1][0] if pts else '-'}")
    last = max(date.fromisoformat(d) for d, _ in s.get("vix", [("2026-01-01", 0)]))
    print(f"\n기준: 수준=지난 {rg.LOOKBACK}거래일 중 상·하위 {int(rg.LEVEL_PCT * 100)}% · 방향=최근 {rg.WINDOW}거래일 변화가 평소 "
          f"{rg.WINDOW}일 변화의 표준편차 {rg.Z}배 이상 · 표본 {rg.MIN_OBS}일 미만은 데이터 부족")
    for market in ("US", "KR"):
        print(f"\n== {market} - 지난 {WEEKS}주(금요일 기준) ==")
        head = " | ".join(f"{name}" for _, name, _ in rg.AXES[market])
        print(f"  주       | {head} | 조합")
        for f in fridays(last, WEEKS):
            st = rg.market_state(s, market, f)
            cells = []
            for axis, _, key in rg.AXES[market]:
                a = st["axes"][axis]
                lv = {"high": "높", "mid": "중", "low": "낮"}.get(a["level"], "?")
                if key == "kospi_foreign":
                    lv = {"high": "+", "low": "−", "mid": "0"}.get(a["level"], "?")
                cells.append(f"{rg.ARROW[a['dir']]}{lv} {fmt_val(key, a['value'])}")
            print(f"  {f[5:]}   | " + " | ".join(cells) + " | " + (", ".join(c["name"] for c in st["combos"]) or "-"))
        st = rg.market_state(s, market, fridays(last, 1)[0])
        print("  최근 주 자세히:")
        for axis, a in st["axes"].items():
            print(f"    {a['name']:<8} {a['label']:<24} 값 {fmt_val(a['key'], a['value'])} · 4주 변화 {fmt_val(a['key'], a['chg'])} · "
                  f"z {a['z']} · {rg.LEVEL_KO[a['level']]} · {rg.ARROW[a['dir']]} (표본 {a['n']})")
        for k, c in st["context"].items():
            print(f"    (참고) {rg.LABEL_KO.get(k, k):<24} 값 {fmt_val(k, c['value'])} · 4주 변화 {fmt_val(k, c['chg'])} · "
                  f"{rg.LEVEL_KO[c['level']]} · {rg.ARROW[c['dir']]}")
        cnt, judged = Counter(), 0
        for f in fridays(last, FREQ_WEEKS):
            st = rg.market_state(s, market, f)
            if all(a["dir"] is not None for a in st["axes"].values()):
                judged += 1
            for c in st["combos"]:
                cnt[c["name"]] += 1
            if not st["combos"]:
                cnt["(이름 없음)"] += 1
        print(f"  지난 {FREQ_WEEKS}주 조합 빈도(모든 축 판정 가능한 주 {judged}): " + " · ".join(f"{k} {v}" for k, v in cnt.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
