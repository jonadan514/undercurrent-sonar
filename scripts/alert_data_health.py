"""데이터 상태가 늦거나 없으면 텔레그램으로 알린다(2026-11-18, 사용자: 다른 예약 실행 점검 후 알림).

판정은 사이트의 데이터 상태 API(/api/data/health - 사이드바 '데이터 N개 모두 정상'과 같은 것) 하나만 쓴다. 데이터마다 허용 일수
(매일 3~4일, 매주 9~15일 등)가 거기 있어, GitHub 예약이 몇 시간 밀리는 정도로는 울리지 않고 실제로 갱신이 멈춘 것만 걸린다.
14일 점검(11/18): 정기 작업이 빠진 날은 거의 없고 매일 작업이 최대 10시간 늦게 돌았다 - 그 정도는 정상으로 둔다.

한국 뉴스 이어 돌기(collect-kr-news-intraday)가 매 차례 부르고, 같은 날(한국 시간) 같은 내용이면 다시 보내지 않는다
(health_alerts 표). 정상으로 돌아오면 한 번 알린다.

    python scripts/alert_data_health.py            # 늦은 게 있으면 보냄
    python scripts/alert_data_health.py --dry-run  # 보내지 않고 출력만
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db.turso_http import execute, query  # noqa: E402

HEALTH_URL = "https://u-sonar.vercel.app/api/data/health"
DDL = """CREATE TABLE IF NOT EXISTS health_alerts (
  day TEXT NOT NULL,          -- 한국 날짜
  body TEXT NOT NULL,
  sent_at TEXT NOT NULL,
  PRIMARY KEY (day, body)
)"""
MARK = {"late": "늦음", "missing": "없음"}


def problems(health: dict) -> list[dict]:
    return [it for it in health.get("items", []) if it.get("status") in MARK]


def message(items: list[dict]) -> str:
    lines = [f"⚠️ <b>U-Sonar 데이터 갱신 멈춤</b> {len(items)}개"]
    for it in items:
        age = f"{it['age_days']}일 전" if it.get("age_days") is not None else "기록 없음"
        lines.append(f"· [{MARK[it['status']]}] {it['label']} - 마지막 {age} (허용 {it['ok_days']}일, {it.get('cadence') or ''})")
    lines.append("\nGitHub → Actions에서 해당 작업이 돌았는지 확인해 주세요. 상태 화면: https://u-sonar.vercel.app/status")
    return "\n".join(lines)


def send(text: str) -> None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        print("텔레그램 설정 없음 - 출력만", flush=True)
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=20).read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=60) as r:
            health = json.load(r)
    except Exception as e:  # noqa: BLE001 - 사이트가 잠깐 안 열리면 다음 차례에
        print(f"데이터 상태를 못 읽음({type(e).__name__}) - 다음 차례에", flush=True)
        return 0
    bad = problems(health)
    s = health.get("summary", {})
    print(f"데이터 상태: 전체 {s.get('total')} · 정상 {s.get('ok')} · 늦음 {s.get('late')} · 없음 {s.get('missing')}", flush=True)
    day = (datetime.now(timezone.utc) + timedelta(hours=9)).date().isoformat()
    body = ",".join(sorted(f"{it['key']}:{it['status']}" for it in bad)) or "ok"
    if args.dry_run:
        print(message(bad) if bad else "모두 정상", flush=True)
        return 0
    execute(DDL)
    last = query("SELECT body FROM health_alerts ORDER BY sent_at DESC LIMIT 1")
    last_body = last[0]["body"] if last else "ok"
    if body == "ok" and last_body == "ok":
        return 0
    if query("SELECT 1 FROM health_alerts WHERE day = ? AND body = ?", [day, body]):
        return 0   # 오늘 같은 내용은 이미 보냄
    if body == "ok":
        text = "✅ <b>U-Sonar 데이터 갱신</b> 다시 모두 정상입니다."
    else:
        text = message(bad)
    send(text)
    execute("INSERT OR IGNORE INTO health_alerts (day, body, sent_at) VALUES (?, ?, ?)",
            [day, body, datetime.now(timezone.utc).isoformat()])
    print("알림 보냄:\n" + text, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
