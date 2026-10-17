"""S&P 500·400 구성종목 목록(data/sp500_list.csv, data/sp400_list.csv)을 위키백과에서 다시 받아 갱신한다 (2026-10-17).

왜: 미국 유니버스(watchlist_collector.get_us_universe)는 저장소의 이 두 파일을 읽는데, 파일이 9월 이후 그대로라
지수에서 빠진 종목(예: 비상장 전환된 EA)이 워치리스트 후보로 계속 나왔다. 주간 분석(run_integrated_analysis)도
목록을 받지만 실행 환경에서만 쓰고 저장소에 남기지 않는다.

안전장치: 위키백과는 누구나 고칠 수 있고 표 구조도 바뀔 수 있다 -> 받은 목록이 정상 범위(종목 수)를 벗어나거나
한 번에 너무 많이 바뀌면 파일을 건드리지 않고 실패로 끝낸다(정기 실행이면 텔레그램 실패 알림).
바뀐 종목이 있으면 목록과 함께 텔레그램으로 알린다(TELEGRAM_* 없으면 건너뜀).

    python scripts/refresh_us_index_lists.py            # 받아서 비교·저장
    python scripts/refresh_us_index_lists.py --dry-run  # 비교만
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# (파일, 정상 종목 수 범위, 한 번에 허용하는 최대 변경 수(편입+제외))
LISTS = {
    "sp500": (ROOT / "data" / "sp500_list.csv", (490, 515), 30),
    "sp400": (ROOT / "data" / "sp400_list.csv", (390, 410), 40),
}


def _log(msg: str) -> None:
    print(f"[universe] {msg}", flush=True)


def diff_lists(old: list[str], new: list[str]) -> tuple[list[str], list[str]]:
    o, n = set(old), set(new)
    return sorted(n - o), sorted(o - n)


def check(name: str, new: list[str], added: list[str], removed: list[str], allow_large: bool = False) -> str | None:
    """이상하면 이유, 정상이면 None."""
    _, (lo, hi), max_change = LISTS[name]
    if not lo <= len(new) <= hi:
        return f"{name} 종목 수 {len(new)}개 - 정상 범위 {lo}-{hi} 밖(위키백과 표 구조 변경 의심)"
    if len(set(new)) != len(new):
        return f"{name} 중복 티커가 있다"
    if not allow_large and len(added) + len(removed) > max_change:
        return f"{name} 한 번에 {len(added) + len(removed)}개 변경 - 허용 {max_change}개 초과(문서 훼손 의심)"
    return None


def _fetch(name: str) -> pd.DataFrame:
    if name == "sp500":
        from src.collectors.fetch_sp500_list import fetch_sp500_list
        return fetch_sp500_list()
    from src.collectors.fetch_sp400_list import fetch_sp400_list
    return fetch_sp400_list()


def _telegram(text: str) -> None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return
    body = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
    except Exception as e:  # noqa: BLE001
        _log(f"텔레그램 발송 실패: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-large", action="store_true",
                    help="변경 수 상한만 무시한다(정기 재조정으로 실제로 많이 바뀐 주 - 로그로 목록을 확인한 뒤 수동 실행). "
                         "종목 수 범위·중복 검사는 그대로")
    args = ap.parse_args()

    fetched, changes, problems = {}, {}, []
    for name, (path, _, _) in LISTS.items():
        old_df = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["Symbol", "Security", "GICS Sector"])
        new_df = _fetch(name)
        added, removed = diff_lists(old_df["Symbol"].astype(str).tolist(), new_df["Symbol"].astype(str).tolist())
        names = {**dict(zip(old_df["Symbol"].astype(str), old_df["Security"])),
                 **dict(zip(new_df["Symbol"].astype(str), new_df["Security"]))}
        _log(f"{name}: {len(old_df)} -> {len(new_df)}종목, 편입 {len(added)} {added}, 제외 {len(removed)} {removed}")
        problem = check(name, new_df["Symbol"].astype(str).tolist(), added, removed, args.allow_large)
        if problem:
            problems.append(problem)
        fetched[name], changes[name] = new_df, (added, removed, names)

    if problems:
        for p in problems:
            _log(f"중단: {p}")
        return 1          # 파일은 건드리지 않는다
    if not any(a or r for a, r, _ in changes.values()):
        _log("바뀐 종목 없음")
        return 0
    if args.dry_run:
        _log("--dry-run: 저장하지 않음")
        return 0

    lines = ["<b>🔄 미국 유니버스 목록 갱신</b> (S&P 500·400, 다음 스크리닝부터 반영)"]
    for name, (path, _, _) in LISTS.items():
        added, removed, names = changes[name]
        if not (added or removed):
            continue
        fetched[name].to_csv(path, index=False)
        label = "S&P 500" if name == "sp500" else "S&P 400"
        if added:
            lines.append(f"{label} 편입: " + ", ".join(f"{t}({names.get(t, '')})" for t in added))
        if removed:
            lines.append(f"{label} 제외: " + ", ".join(f"{t}({names.get(t, '')})" for t in removed))
    _telegram("\n".join(lines))
    _log("저장 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
