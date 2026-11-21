"""반도체 테마(AI 반도체·반도체 장비·소재, 미국·한국)의 주간 신호가 바뀐 주에만 텔레그램으로 알린다
(2026-11-21, 사용자: 반도체 테마랑 환율·금리·VIX 급변할 때만 - TIGER 반도체TOP10 보유).

일요일 정기 계산(뉴스·실적·주가·라벨)이 끝난 뒤 send-radar-digest 워크플로에서 돈다.
방금 계산한 주와 그 전 주의 theme_signals를 비교해 축 화살표(뉴스·실적·주가)나 라벨이 바뀐 테마가 하나라도 있으면
네 줄(2테마 × 2시장)을 모두 보여 주고 바뀐 칸을 표시한다. 바뀐 게 없으면 보내지 않는다.
값이 없던 축(na·빈 값)이 생기거나 없어지는 것은 변화로 치지 않는다(한국 뉴스 축은 12/14 주부터 다시 나온다 - 수집 방식 전환).
점수·등급 없음(원칙 1) - 세 축을 따로 보여 준다.

    python scripts/alert_semi_themes.py --dry-run
    python scripts/alert_semi_themes.py --notify
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.db.data_store import get_db  # noqa: E402
from src.db.theme_signals import signal_week_monday  # noqa: E402
from src.analyzers.theme_labels import label_display  # noqa: E402

THEMES = ["ai_semiconductor", "semi_equipment"]
MARKETS = [("KR", "🇰🇷"), ("US", "🇺🇸")]
AXES = [("news_arrow", "뉴스"), ("earn_arrow", "실적"), ("price_arrow", "주가")]
ARROW = {"up2": "↑↑", "up1": "↑", "flat": "→", "down": "↓"}
SITE = "https://u-sonar.vercel.app/radar"


def _log(msg: str) -> None:
    print(f"[semi-alert] {msg}", flush=True)


def _a(v: str | None) -> str | None:
    return v if v in ARROW else None   # na·빈 값은 값 없음


def diff(cur: dict, prev: dict | None) -> list[str]:
    """바뀐 칸 이름 목록. 값이 없던 축이 생기거나 없어지는 것은 빼고, 라벨은 생기고 없어지는 것도 변화."""
    if not prev:
        return []
    out = [name for col, name in AXES if _a(cur.get(col)) and _a(prev.get(col)) and _a(cur.get(col)) != _a(prev.get(col))]
    if (cur.get("label") or None) != (prev.get("label") or None):
        out.append("라벨")
    return out


def line(name: str, flag: str, cur: dict | None, prev: dict | None, changed: list[str]) -> str:
    if not cur:
        return f"{flag} {name}: 이번 주 값 없음"
    cells = []
    for col, ax in AXES:
        now = ARROW.get(_a(cur.get(col)) or "", "–")
        if ax in changed:
            cells.append(f"<b>{ax} {ARROW.get(_a(prev.get(col)) or '', '–')}에서 {now}로</b>")
        else:
            cells.append(f"{ax} {now}")
    lab = cur.get("label")
    if "라벨" in changed:
        before = label_display(prev.get("label")) if prev and prev.get("label") else "없음"
        cells.append(f"<b>라벨 {before}에서 {label_display(lab) if lab else '없음'}으로</b>")
    elif lab:
        cells.append(f"라벨 {label_display(lab)}")
    mark = "🔸 " if changed else ""
    return f"{mark}{flag} {name}: " + " · ".join(cells)


def _rows(conn, week: str) -> dict[tuple[str, str], dict]:
    q = ("SELECT theme_id, market, news_arrow, earn_arrow, price_arrow, label FROM theme_signals WHERE week_start = ? "
         f"AND theme_id IN ({','.join('?' * len(THEMES))})")
    out = {}
    for tid, m, n, e, p, lab in conn.execute(q, (week, *THEMES)).fetchall():
        out[(tid, m)] = {"news_arrow": n, "earn_arrow": e, "price_arrow": p, "label": lab}
    return out


def send_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        _log("TELEGRAM_* 미설정 - 발송 건너뜀")
        return
    body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()
    _log("텔레그램 발송 완료")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--week", help="비교할 주 월요일(기본: 방금 계산한 주)")
    args = ap.parse_args()

    week = args.week or signal_week_monday(date.today()).isoformat()
    prev_week = (date.fromisoformat(week) - timedelta(days=7)).isoformat()
    names = {t["id"]: t["name_ko"] for t in yaml.safe_load(open(ROOT / "config" / "themes.yaml", encoding="utf-8"))["themes"]}
    conn = get_db()
    cur, prev = _rows(conn, week), _rows(conn, prev_week)
    if not cur and args.dry_run and not args.week:
        # 점검용: 이번 주가 아직 계산 전이면(일요일 정기 실행 전) 마지막으로 계산된 주로 문구를 본다. 정기 발송은 이렇게 하지 않는다
        # (계산이 실패한 주에 지난 주 변화를 다시 보내지 않게).
        last = conn.execute(f"SELECT MAX(week_start) FROM theme_signals WHERE price_arrow IS NOT NULL "
                            f"AND theme_id IN ({','.join('?' * len(THEMES))})", tuple(THEMES)).fetchone()[0]
        if last:
            _log(f"{week} 주 값 없음 - 점검용으로 마지막 계산 주 {last}")
            week, prev_week = str(last), (date.fromisoformat(str(last)) - timedelta(days=7)).isoformat()
            cur, prev = _rows(conn, week), _rows(conn, prev_week)
    if not cur:
        _log(f"{week} 주 반도체 테마 값 없음 - 보내지 않음")
        return 0

    lines, any_change = [], False
    for market, flag in MARKETS:
        for tid in THEMES:
            c, p = cur.get((tid, market)), prev.get((tid, market))
            ch = diff(c, p) if c else []
            any_change |= bool(ch)
            lines.append(line(names.get(tid, tid), flag, c, p, ch))
            _log(f"{market} {tid}: 이번 {c} · 전주 {p} · 바뀜 {ch or '없음'}")
    if not any_change:
        _log("바뀐 칸 없음 - 보내지 않음")
        return 0
    d = date.fromisoformat(week)
    text = "\n".join([f"🔬 <b>반도체 테마 신호 변화</b> · {d.month}/{d.day} 주",
                      "전주와 달라진 칸만 굵게 (🔸 바뀐 줄)", "↑↑ 크게 좋아짐 · ↑ 좋아짐 · → 비슷 · ↓ 나빠짐 · – 값 없음", "", *lines, "",
                      f'<a href="{SITE}">테마 레이더에서 보기</a>'])
    _log(text)
    if args.dry_run or not args.notify:
        _log("발송 안 함(dry-run 또는 --notify 없음)")
        return 0
    send_telegram(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
