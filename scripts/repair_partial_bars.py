"""한국 결과 중 '장중 가격'으로 채워진 칸을 비운다 - 다음 결과 계산이 완성된 종가로 다시 채운다 (2026-10-26 점검).

성적표(compute_pick_returns)·신호 사후 확인(compute_signal_outcomes)은 정기 실행이 월요일 00~02시 UTC, 곧 한국 장중에 돌았다.
그 시각 yfinance가 주는 '오늘 막대'의 종가는 장중 가격인데, 끝가(또는 지수 시작가)가 그날이면 그 값으로 채워지고
COALESCE(이미 채운 값은 그대로)로 굳었다. 두 스크립트는 이제 오늘 막대를 쓰지 않는다(signal_check.completed_bars).

여기서는 그런 실행이 있었던 날(POLLUTED_DAYS, GitHub 실행 기록에서 한국 장중 00:00~07:10 UTC에 시작한 날)을 끝가로 쓴 칸만 NULL로 만든다.
- kr_pick_returns: fwd_{h}d_ret (시작가는 스크리닝 때 적은 가격이라 그대로)
- kr_benchmark_returns: 시작 막대가 그날이면 entry_price와 모든 기간, 아니면 끝 막대가 그날인 기간만
- signal_outcomes(KR): ret_{h}d·bench_{h}d, signal_universe_returns(KR): univ_{h}d·n_{h}d
성적표 표는 실행마다 새 값으로 덮어쓰지만(COALESCE(새 값, 옛 값)) 오늘 막대를 빼면 끝 날짜가 오늘인 칸은 새 값이 NULL이라 옛 장중 값이
남는다 - 그래서 같이 비운다. 신호 원본(signal_log)·후보 이력(watchlist_candidate_history)은 건드리지 않는다(원칙 5). 비운 칸은 계산 결과일 뿐이라 다시 계산된다 -
제대로 채워졌던 칸을 비워도(경계에 걸린 날) 같은 값으로 다시 채워질 뿐이다. 미국은 장중 실행이 없어 해당 없음.

    python scripts/repair_partial_bars.py            # 몇 칸인지 보기만
    python scripts/repair_partial_bars.py --apply    # 비우기
"""
from __future__ import annotations

import argparse
import sys
from bisect import bisect_left
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.compute_pick_returns import HORIZONS as PICK_HORIZONS
from src.analyzers.signal_check import HORIZONS as SIGNAL_HORIZONS
from src.analyzers.signal_check import completed_bars

POLLUTED_DAYS = ("2026-08-21", "2026-08-31", "2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28", "2026-09-30",
                 "2026-10-05", "2026-10-12", "2026-10-19", "2026-10-21", "2026-10-26")


def _log(msg: str) -> None:
    print(f"[repair-partial] {msg}", flush=True)


def end_bar(calendar: list[str], d: str) -> str | None:
    """d 이후 첫 거래일(fwd_return·_price_on_or_after와 같은 규칙)."""
    i = bisect_left(calendar, d)
    return calendar[i] if i < len(calendar) else None


def plan(calendar: list[str], polluted: set[str], pick_rows, bench_rows, sig_rows, univ_rows) -> dict[str, list]:
    """비울 칸 목록. 각 rows는 (키..., 값...) 튜플 - 값이 NULL인 칸은 건너뛴다."""
    def hit(start: str, h: int) -> bool:
        return end_bar(calendar, (date.fromisoformat(start) + timedelta(days=h)).isoformat()) in polluted

    out: dict[str, list] = {"pick": [], "bench": [], "signal": [], "univ": []}
    for d, symbol, *vals in pick_rows:
        cols = [f"fwd_{h}d_ret" for h, v in zip(PICK_HORIZONS, vals) if v is not None and hit(d, h)]
        if cols:
            out["pick"].append(((d, symbol), cols))
    for d, entry, *vals in bench_rows:
        if entry is not None and end_bar(calendar, d) in polluted:
            out["bench"].append(((d,), ["entry_price"] + [f"fwd_{h}d_ret" for h in PICK_HORIZONS]))
            continue
        cols = [f"fwd_{h}d_ret" for h, v in zip(PICK_HORIZONS, vals) if v is not None and hit(d, h)]
        if cols:
            out["bench"].append(((d,), cols))
    for week, kind, symbol, *vals in sig_rows:
        cols = [c for h, r, b in zip(SIGNAL_HORIZONS, vals[0::2], vals[1::2])
                if (r is not None or b is not None) and hit(week, h) for c in (f"ret_{h}d", f"bench_{h}d")]
        if cols:
            out["signal"].append(((week, kind, symbol), cols))
    for week, *vals in univ_rows:
        cols = [c for h, v in zip(SIGNAL_HORIZONS, vals) if v is not None and hit(week, h) for c in (f"univ_{h}d", f"n_{h}d")]
        if cols:
            out["univ"].append(((week,), cols))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 비운다(기본은 몇 칸인지 보기만)")
    args = ap.parse_args()

    from src.collectors.us_price_fetcher import USPriceFetcher
    from src.db.data_store import get_db

    today = date.today()
    df = USPriceFetcher().fetch_ohlcv("^KS11", period="2y")
    if df is None or df.empty:
        _log("^KS11 가격을 못 받음 - 거래일을 몰라 중단")
        return 1
    calendar = [d for d, _ in completed_bars([(d.strftime("%Y-%m-%d"), 0.0) for d in df.index], today)]
    # 오늘이 장중 실행일이면 오늘 막대는 아직 완성 전이라 거래일 목록에 없다 - 그날을 끝가로 쓴 칸을 찾으려고 넣는다
    calendar += [d for d in POLLUTED_DAYS if d > calendar[-1]]
    polluted = set(POLLUTED_DAYS)
    _log(f"한국 거래일 {len(calendar)}일({calendar[0]}~{calendar[-1]}), 장중 실행일 {len(polluted)}일")

    conn = get_db()
    pc = ", ".join(f"fwd_{h}d_ret" for h in PICK_HORIZONS)
    sc = ", ".join(f"ret_{h}d, bench_{h}d" for h in SIGNAL_HORIZONS)
    uc = ", ".join(f"univ_{h}d" for h in SIGNAL_HORIZONS)
    todo = plan(calendar, polluted,
                conn.execute(f"SELECT date, symbol, {pc} FROM kr_pick_returns").fetchall(),
                conn.execute(f"SELECT date, entry_price, {pc} FROM kr_benchmark_returns").fetchall(),
                conn.execute(f"SELECT week, kind, symbol, {sc} FROM signal_outcomes WHERE market = 'KR'").fetchall(),
                conn.execute(f"SELECT week, {uc} FROM signal_universe_returns WHERE market = 'KR'").fetchall())
    where = {"pick": ("kr_pick_returns", "date = ? AND symbol = ?"),
             "bench": ("kr_benchmark_returns", "date = ?"),
             "signal": ("signal_outcomes", "market = 'KR' AND week = ? AND kind = ? AND symbol = ?"),
             "univ": ("signal_universe_returns", "market = 'KR' AND week = ?")}
    for key, items in todo.items():
        table, cond = where[key]
        by_col: dict[str, int] = {}
        for _, cols in items:
            for c in cols:
                by_col[c] = by_col.get(c, 0) + 1
        _log(f"{table}: {len(items)}줄 {by_col}" + (f" 예: {items[0][0]}" if items else ""))
        if args.apply:
            for k, cols in items:
                conn.execute(f"UPDATE {table} SET {', '.join(f'{c} = NULL' for c in cols)}, updated_at = datetime('now') "
                             f"WHERE {cond}", k)
    if args.apply:
        conn.commit()
        _log("비움 - Performance Tracking을 돌리면 완성된 종가로 다시 채운다(오늘 막대는 다음 주)")
    else:
        _log("보기만 함(--apply 없음)")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
