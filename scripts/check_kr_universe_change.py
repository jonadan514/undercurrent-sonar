"""한국 유니버스(data/kr_universe.json) 갱신 전후 비교 - 이상하면 되돌리고 실패, 정상이면 바뀐 종목을 알린다 (2026-10-17).

refresh-universe-data.yml이 pykrx로 새 유니버스를 받은 직후 돈다. 시가총액 하한(기본 3000억) 근처 종목은 매주
들고 나는 게 정상이라 소폭 변경은 그대로 받고, KRX 응답 이상(빈 목록·절반 증발 등)으로 보이는 큰 변화만 막는다.

    python scripts/check_kr_universe_change.py --old /tmp/kr_universe_old.json --new data/kr_universe.json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import urllib.request

MAX_COUNT_SWING = 0.15   # 종목 수가 이보다 크게 바뀌면 이상
MAX_CHANGES = 150        # 편입+제외 합이 이보다 많으면 이상
SHOW = 8                 # 알림에 이름을 보여 줄 최대 개수


def _log(msg: str) -> None:
    print(f"[kr-universe] {msg}", flush=True)


def compare(old: list[dict], new: list[dict]) -> tuple[list[dict], list[dict]]:
    o = {i["symbol"]: i for i in old}
    n = {i["symbol"]: i for i in new}
    added = sorted((n[s] for s in n.keys() - o.keys()), key=lambda i: -(i.get("market_cap") or 0))
    removed = sorted((o[s] for s in o.keys() - n.keys()), key=lambda i: -(i.get("market_cap") or 0))
    return added, removed


def check(old: list[dict], new: list[dict], added: list, removed: list) -> str | None:
    if not new:
        return "새 유니버스가 비어 있다"
    if old and abs(len(new) - len(old)) / len(old) > MAX_COUNT_SWING:
        return f"종목 수 {len(old)} -> {len(new)} - {MAX_COUNT_SWING:.0%} 넘게 바뀜(KRX 응답 이상 의심)"
    if len(added) + len(removed) > MAX_CHANGES:
        return f"한 번에 {len(added) + len(removed)}개 변경 - 허용 {MAX_CHANGES}개 초과"
    return None


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


def _names(items: list[dict]) -> str:
    out = ", ".join(i.get("name") or i["symbol"] for i in items[:SHOW])
    return out + (f" 외 {len(items) - SHOW}개" if len(items) > SHOW else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--notify", action="store_true", help="바뀐 종목을 텔레그램으로 알린다")
    args = ap.parse_args()
    old = json.load(open(args.old, encoding="utf-8")).get("items") or []
    new = json.load(open(args.new, encoding="utf-8")).get("items") or []
    added, removed = compare(old, new)
    _log(f"{len(old)} -> {len(new)}종목, 편입 {len(added)}, 제외 {len(removed)}")
    _log(f"  편입: {[i['symbol'] + ' ' + (i.get('name') or '') for i in added]}")
    _log(f"  제외: {[i['symbol'] + ' ' + (i.get('name') or '') for i in removed]}")
    problem = check(old, new, added, removed)
    if problem:
        shutil.copyfile(args.old, args.new)   # 새 파일을 버리고 이전 유니버스로 되돌린다
        _log(f"중단: {problem} - 이전 유니버스로 되돌림")
        return 1
    if args.notify and (added or removed):
        lines = [f"<b>🔄 한국 유니버스 갱신</b> {len(old)} → {len(new)}종목 (다음 스크리닝부터 반영)"]
        if added:
            lines.append(f"편입 {len(added)}: {_names(added)}")
        if removed:
            lines.append(f"제외 {len(removed)}: {_names(removed)}")
        _telegram("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
