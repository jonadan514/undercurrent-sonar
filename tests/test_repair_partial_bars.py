from datetime import date

import pandas as pd

from scripts.compute_pick_returns import _completed
from scripts.repair_partial_bars import end_bar, plan

CAL = ["2026-09-25", "2026-09-28", "2026-09-29", "2026-10-23", "2026-10-26"]
POLLUTED = {"2026-09-28", "2026-10-26"}


def test_end_bar_next_trading_day():
    assert end_bar(CAL, "2026-09-26") == "2026-09-28"
    assert end_bar(CAL, "2026-10-24") == "2026-10-26"
    assert end_bar(CAL, "2026-10-27") is None


def test_plan_clears_only_cells_ending_on_intraday_days():
    nones = [None] * 5
    pick = [("2026-09-24", "005930", 0.05, *nones),      # +30 = 10/24(토) → 10/26 장중
            ("2026-09-23", "000660", 0.02, *nones),      # +30 = 10/23 → 그대로
            ("2026-08-25", "035420", None, None, *([None] * 4))]  # 값 없음 → 건너뜀
    bench = [("2026-09-28", 2500.0, 0.01, *nones),       # 시작 막대가 장중 → 시작가·모든 기간
             ("2026-09-24", 2400.0, 0.03, *nones)]       # 끝 막대만 장중
    sig = [("2026-09-28", "insider_buy", "005930", 0.1, 0.02, None, None),   # +28 = 10/26
           ("2026-09-21", "insider_buy", "000660", 0.1, 0.02, None, None)]   # +28 = 10/19 → 장중 아님(목록에 없음)
    univ = [("2026-09-28", -0.12, None), ("2026-09-21", -0.02, None)]
    out = plan(CAL, POLLUTED, pick, bench, sig, univ)
    assert out["pick"] == [(("2026-09-24", "005930"), ["fwd_30d_ret"])]
    assert out["bench"][0] == (("2026-09-28",), ["entry_price", "fwd_30d_ret", "fwd_60d_ret", "fwd_90d_ret",
                                                  "fwd_180d_ret", "fwd_365d_ret", "fwd_730d_ret"])
    assert out["bench"][1] == (("2026-09-24",), ["fwd_30d_ret"])
    assert out["signal"] == [(("2026-09-28", "insider_buy", "005930"), ["ret_28d", "bench_28d"])]
    assert out["univ"] == [(("2026-09-28",), ["univ_28d", "n_28d"])]


def test_pick_returns_drop_today_bar():
    df = pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=pd.to_datetime(["2026-10-22", "2026-10-23", "2026-10-26"]))
    assert list(_completed(df, date(2026, 10, 26))["Close"]) == [1.0, 2.0]
    assert _completed(None, date(2026, 10, 26)) is None
