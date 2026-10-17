"""매크로 일별 이력 (src/analyzers/macro_snapshot.py history_rows·split_settled)."""
import pandas as pd

from src.analyzers.macro_snapshot import history_rows, split_settled


def test_history_rows_drop_nan_and_round():
    s = pd.Series([4.1234567, float("nan"), 4.2], index=pd.to_datetime(["2026-10-13", "2026-10-14", "2026-10-15"]))
    assert history_rows({"us10y": s}) == [("2026-10-13", "us10y", 4.1235), ("2026-10-15", "us10y", 4.2)]


def test_split_settled_recent_days_replaceable():
    rows = [("2026-10-09", "wti", 90.0), ("2026-10-12", "wti", 95.0), ("2026-10-16", "wti", 101.4)]
    settled, recent = split_settled(rows, "2026-10-16", settle_days=5)
    assert [r[0] for r in settled] == ["2026-10-09"] and [r[0] for r in recent] == ["2026-10-12", "2026-10-16"]
