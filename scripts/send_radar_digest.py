"""Phase A-6: 라벨 붙은 테마 주간 요약을 텔레그램으로 발송.

SPEC: docs/radar/SPEC_phase_a_signals.md §7 step 6
뉴스/실적/주가/라벨 계산이 전부 끝난 뒤(일요일 22:45 UTC 이후) 돌아야 한다.

Usage:
  python scripts/send_radar_digest.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.db.data_store import get_db
from src.db.theme_signals import signal_week_monday
from src.analyzers.theme_labels import label_display

THEMES_YAML = ROOT / "config" / "themes.yaml"
RADAR_URL = "https://u-sonar.vercel.app/radar"

# SPEC §6.2 순서 그대로 - 순위가 아니라 편집 방침.
LABEL_ORDER = ["Quiet Strength", "Quiet Recovery", "Early Buzz", "Full Alignment", "Overheated Buzz", "Full Decline"]
LABEL_EMOJI = {
    "Quiet Strength": "🟢", "Quiet Recovery": "🔵", "Early Buzz": "🟡",
    "Full Alignment": "🟠", "Overheated Buzz": "🔴", "Full Decline": "⚫",
}
ARROW_GLYPH = {"up2": "↑↑", "up1": "↑", "flat": "→", "down": "↓", "na": "–"}


def _log(msg: str) -> None:
    print(f"[digest] {msg}")


def load_theme_names() -> dict[str, str]:
    with open(THEMES_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {t["id"]: t["name_ko"] for t in data["themes"]}


def arrow(a: str | None) -> str:
    return ARROW_GLYPH.get(a or "na", "–")


def send_telegram(text: str) -> None:
    """다른 스크립트(run_watchlist_screen.py)와 동일한 패턴 - 미설정이면 조용히 건너뜀."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        _log("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 미설정 - 발송 건너뜀")
        return

    body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        _log("텔레그램 발송 완료")
    except Exception as e:
        _log(f"텔레그램 발송 실패: {e}")


def main() -> None:
    conn = get_db()
    week_start = signal_week_monday(date.today()).isoformat()

    rows = conn.execute(
        """
        SELECT theme_id, news_arrow, earn_arrow, price_arrow, label,
               earn_members, earn_improved, market
        FROM theme_signals
        WHERE market IN ('US', 'KR') AND week_start = ? AND label IS NOT NULL
        """,
        (week_start,),
    ).fetchall()
    conn.close()

    if not rows:
        _log(f"{week_start}: 라벨 붙은 테마 없음 - 발송 건너뜀")
        return

    names = load_theme_names()

    # 시장별로 섹션을 나눈다 - 같은 테마(예: 반도체 장비)가 미국/한국에서
    # 서로 다른 라벨을 받을 수 있어, 섞어 놓으면 어느 시장 얘기인지 헷갈린다.
    _y, _m, _d = week_start.split("-")
    lines = [f"📡 <b>U-Sonar 테마 레이더</b> · {int(_m)}/{int(_d)} 주", f"라벨 붙은 테마 {len(rows)}개\n"]
    for market, flag in (("US", "🇺🇸"), ("KR", "🇰🇷")):
        market_rows = [r for r in rows if r[7] == market]
        if not market_rows:
            continue
        lines.append(f"{flag} <b>{market}</b> ({len(market_rows)}개)")

        by_label: dict[str, list] = {}
        for r in market_rows:
            by_label.setdefault(r[4], []).append(r)

        for label in LABEL_ORDER:
            items = by_label.get(label)
            if not items:
                continue
            lines.append(f"{LABEL_EMOJI.get(label, '•')} <b>{label_display(label)}</b>")
            for theme_id, news_a, earn_a, price_a, _label, earn_members, earn_improved, _mkt in items:
                name = names.get(theme_id, theme_id)
                detail = f"({earn_members}개사 중 {earn_improved}개 중앙값 초과)" if earn_members is not None else ""
                lines.append(f"  • {name}: 뉴스{arrow(news_a)} 실적{arrow(earn_a)} 주가{arrow(price_a)} {detail}")
            lines.append("")

    lines.append(f'<a href="{RADAR_URL}">전체 보기</a>')
    text = "\n".join(lines)

    _log(text)
    send_telegram(text)


if __name__ == "__main__":
    main()
