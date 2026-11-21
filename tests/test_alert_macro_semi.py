"""급변 알림(alert_macro_moves)·반도체 테마 변화 알림(alert_semi_themes)의 판단 부분 (2026-11-21)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import alert_macro_moves as mm  # noqa: E402
import alert_semi_themes as st  # noqa: E402


def _wiggle(n, base=1400.0, step=2.0):
    return [base + (step if i % 2 else -step) for i in range(n)]


def test_detect_short_history_is_insufficient():
    assert mm.detect(_wiggle(100), "pct") == {}


def test_detect_flags_big_one_day_move_only():
    vals = _wiggle(300)
    calm = mm.detect(vals, "pct")
    assert calm and not any(r["hit"] for r in calm.values())
    jump = mm.detect(vals + [vals[-1] * 1.02], "pct")   # 평소 ±0.3% 흔들림에 +2%
    assert jump[1]["hit"] and jump[1]["ratio"] > 2


def test_detect_abs_for_rates_and_down_moves():
    vals = [4.0 + (0.01 if i % 2 else -0.01) for i in range(300)] + [3.8]
    r = mm.detect(vals, "abs")
    assert r[1]["hit"] and r[1]["ratio"] < -2


def test_build_line_formats_won_and_ratio():
    vals = _wiggle(300) + [1450.0]
    res = mm.detect(vals, "pct")
    s = mm.build_line("원/달러 환율", "원", "pct", "2026-11-20", vals, res)
    assert "1,450.0원" in s and "(11/20)" in s and "⚠️ 하루" in s and "평소의" in s


def test_semi_diff_ignores_missing_axes_but_counts_label():
    prev = {"news_arrow": "na", "earn_arrow": "up1", "price_arrow": "down", "label": None}
    cur = {"news_arrow": "up1", "earn_arrow": "up1", "price_arrow": "down", "label": None}
    assert st.diff(cur, prev) == []                       # 뉴스 축이 새로 생긴 것은 변화 아님
    cur2 = {**cur, "earn_arrow": "up2", "label": "Quiet Strength"}
    assert st.diff(cur2, prev) == ["실적", "라벨"]
    assert st.diff(cur2, None) == []                      # 전주 값이 없으면 비교하지 않음


def test_semi_line_bolds_changed_cells():
    prev = {"news_arrow": None, "earn_arrow": "up1", "price_arrow": "down", "label": None}
    cur = {"news_arrow": None, "earn_arrow": "up2", "price_arrow": "down", "label": None}
    s = st.line("AI 반도체", "🇰🇷", cur, prev, st.diff(cur, prev))
    assert s.startswith("🔸 🇰🇷 AI 반도체") and "<b>실적 ↑에서 ↑↑로</b>" in s and "주가 ↓" in s and "뉴스 –" in s
