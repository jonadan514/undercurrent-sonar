"""검토 기록 결과 모음(decision_digest) - 주간 텔레그램·월간 보고서 공통 (2026-11-21)."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.analyzers import decision_digest as dd  # noqa: E402


def _row(i, dec, entry, **vals):
    r = {"id": i, "market": "US", "symbol": f"S{i}", "name": None, "decision": dec, "decided_on": entry, "entry_date": entry}
    for h in dd.HORIZONS:
        r[f"ret_{h}d"] = vals.get(f"ret_{h}d")
        r[f"mkt_{h}d"] = vals.get(f"mkt_{h}d")
    return r


def test_arrivals_only_in_window_and_with_values():
    rows = [_row(1, "watch", "2026-10-01", ret_28d="0.05", mkt_28d="0.01"),     # 끝 10/29
            _row(2, "pass", "2026-10-02", ret_28d=None),                          # 값 없음
            _row(3, "watch", "2026-09-01", ret_28d="-0.02", mkt_28d="0.01")]     # 끝 9/29 - 기간 밖
    arr = dd.arrivals(rows, date(2026, 10, 26), date(2026, 11, 2))
    assert [(x["id"], x["h"]) for x in arr] == [(1, 28)]
    assert abs(arr[0]["ex"] - 0.04) < 1e-9


def test_stats_are_distribution_per_decision():
    rows = [_row(1, "watch", "2026-10-01", ret_28d=0.05, mkt_28d=0.01),
            _row(2, "watch", "2026-10-01", ret_28d=-0.03, mkt_28d=0.01),
            _row(3, "watch", "2026-10-01", ret_28d=0.10, mkt_28d=None),
            _row(4, "pass", "2026-10-01", ret_28d=0.02, mkt_28d=0.01)]
    st = dd.stats(dd.arrivals(rows, date(2026, 10, 1), date(2026, 11, 1)))
    w = next(s for s in st if s["decision"] == "watch")
    assert (w["n"], w["n_ex"], w["beat"]) == (3, 2, 1) and abs(w["med"] - 0.05) < 1e-9
    assert dd.stat_text(w).startswith("관심 3건 +5.0% · 시장 대비") and "2건 중 1건 앞섬" in dd.stat_text(w)


def test_next_arrival_and_empty():
    rows = [_row(1, "hold", "2026-11-04"), _row(2, "watch", "2026-11-10")]
    nx = dd.next_arrival(rows, date(2026, 11, 21))
    assert nx == {"date": "2026-12-02", "h": 28, "n": 1}
    assert dd.digest([], date(2026, 11, 1), date(2026, 12, 1), date(2026, 11, 21)) is None
