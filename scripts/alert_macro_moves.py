"""환율·금리·VIX가 평소보다 크게 움직였을 때만 텔레그램으로 알린다 (2026-11-21, 사용자: 반도체 테마랑 환율·금리·VIX 급변할 때만).

지표: 원/달러(usdkrw), 미국 10년물(us10y), 국고채 3년물(kr3y), VIX(vix). 값은 macro_history·kr_rates에 쌓인 종가 그대로.
'급변' 기준(고정 숫자가 아니라 그 지표의 평소 변화폭 대비 - 시장 환경 계산과 같은 생각):
  - 하루 변화가 지난 1년(250거래일) 하루 변화의 표준편차 2배 이상, 또는
  - 5거래일 변화가 지난 1년 5거래일 변화의 표준편차 2배 이상
  - 금리는 %p 차이, 환율·VIX는 % 변화로 잰다(VIX는 수준이 높을수록 크게 움직여 % 쪽이 고르다).
  - 이력이 120거래일 못 되면 판단하지 않는다(데이터부족 - 알림 없음).
같은 지표·같은 날은 한 번만. 5거래일 변화만 걸린 경우는 그 지표를 지난 7일 안에 알린 적이 없을 때만(며칠 이어 울리지 않게).
보낸 기록은 macro_alerts에 쌓는다(덮어쓰지 않음). 판정·점수 아님 - 움직임의 크기만 알린다.

    python scripts/alert_macro_moves.py --dry-run   # 보내지 않고 출력만
    python scripts/alert_macro_moves.py --notify
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.db.data_store import get_db  # noqa: E402

# (키, 이름, 표, 변화 방식, 단위)
INDICATORS = [
    ("usdkrw", "원/달러 환율", "macro_history", "pct", "원"),
    ("us10y", "미국 10년물 금리", "macro_history", "abs", "%"),
    ("kr3y", "국고채 3년물 금리", "kr_rates", "abs", "%"),
    ("vix", "VIX 변동성지수", "macro_history", "pct", ""),
]
WINDOW = 250      # 지난 1년 거래일
MIN_OBS = 120     # 이보다 짧으면 판단하지 않음
Z = 2.0           # 평소 변화폭(표준편차)의 몇 배부터 '급변'
HORIZONS = (1, 5)
STALE_DAYS = 5    # 마지막 값이 이보다 오래면(수집 멈춤) 알리지 않음 - 데이터 상태 알림이 따로 잡는다
REPEAT_DAYS = 7   # 5일 변화만 걸린 경우, 이 기간 안에 같은 지표를 알렸으면 건너뜀
SITE = "https://u-sonar.vercel.app/"

DDL = """CREATE TABLE IF NOT EXISTS macro_alerts (
  date TEXT NOT NULL, key TEXT NOT NULL, sent_at TEXT NOT NULL, detail TEXT NOT NULL,
  PRIMARY KEY (date, key))"""


def _log(msg: str) -> None:
    print(f"[macro-alert] {msg}", flush=True)


def _change(a: float, b: float, kind: str) -> float | None:
    """b(나중) - a(먼저). pct는 비율(0.012 = 1.2%)."""
    if kind == "pct":
        return None if a == 0 else b / a - 1
    return b - a


def _std(xs: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def detect(values: list[float], kind: str, window: int = WINDOW, min_obs: int = MIN_OBS, z: float = Z) -> dict:
    """날짜순 종가 -> {h: {"chg", "sd", "ratio", "hit"}}. 이력이 짧으면 {}(데이터부족).
    기준 분포는 마지막 변화를 뺀 그 앞 window개 변화(겹치는 구간 포함)."""
    out: dict[int, dict] = {}
    if len(values) < min_obs + 1:
        return out
    for h in HORIZONS:
        chs = [_change(values[i - h], values[i], kind) for i in range(h, len(values))]
        chs = [c for c in chs if c is not None]
        if len(chs) < min_obs:
            continue
        last, hist = chs[-1], chs[-1 - window:-1]
        sd = _std(hist)
        if not sd:
            continue
        ratio = last / sd
        out[h] = {"chg": last, "sd": sd, "ratio": ratio, "hit": abs(ratio) >= z}
    return out


def _fmt_chg(chg: float, kind: str, unit: str, prev: float | None) -> str:
    if kind == "pct":
        s = f"{chg * 100:+.1f}%"
        if unit == "원" and prev is not None:
            s = f"{prev * chg:+,.1f}원, " + s
        return s
    return f"{chg:+.2f}%p"


def _fmt_val(v: float, unit: str) -> str:
    if unit == "원":
        return f"{v:,.1f}원"
    if unit == "%":
        return f"{v:.2f}%"
    return f"{v:.2f}"


def build_line(name: str, unit: str, kind: str, last_date: str, values: list[float], res: dict) -> str:
    """'• 원/달러 환율 1,452.3원 · 하루 +18.3원, +1.3%(평소의 2.6배) · 5일 …'"""
    parts = []
    for h, label in ((1, "하루"), (5, "5일")):
        r = res.get(h)
        if not r:
            continue
        prev = values[-1 - h] if len(values) > h else None
        mark = "⚠️ " if r["hit"] else ""
        parts.append(f"{mark}{label} {_fmt_chg(r['chg'], kind, unit, prev)}(평소의 {abs(r['ratio']):.1f}배)")
    d = date.fromisoformat(last_date)
    return f"• <b>{name}</b> {_fmt_val(values[-1], unit)} ({d.month}/{d.day})\n   " + " · ".join(parts)


def _series(conn, table: str, key: str) -> list[tuple[str, float]]:
    since = (date.today() - timedelta(days=550)).isoformat()
    rows = conn.execute(f"SELECT date, value FROM {table} WHERE key = ? AND date >= ? ORDER BY date", (key, since)).fetchall()
    return [(str(d)[:10], float(v)) for d, v in rows if v is not None]


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
    ap.add_argument("--notify", action="store_true", help="걸린 것이 있으면 텔레그램 발송")
    ap.add_argument("--dry-run", action="store_true", help="보내지도 기록하지도 않고 출력만")
    args = ap.parse_args()

    conn = get_db()
    conn.execute(DDL)
    today = date.today()
    lines, sent_keys = [], []
    for key, name, table, kind, unit in INDICATORS:
        try:
            ser = _series(conn, table, key)
        except Exception as e:  # noqa: BLE001 - 표가 없으면 그 지표만 건너뜀
            _log(f"{key}: 읽기 실패({str(e)[:100]})")
            continue
        if not ser:
            _log(f"{key}: 이력 없음")
            continue
        last_date = ser[-1][0]
        values = [v for _, v in ser]
        res = detect(values, kind)
        desc = ", ".join(f"{h}일 {r['ratio']:+.2f}배{'(걸림)' if r['hit'] else ''}" for h, r in res.items()) or "데이터부족"
        _log(f"{key}: {last_date} {values[-1]} · 이력 {len(values)}일 · {desc}")
        if not res or not any(r["hit"] for r in res.values()):
            continue
        if (today - date.fromisoformat(last_date)).days > STALE_DAYS:
            _log(f"{key}: 마지막 값이 {last_date} - 오래돼 알리지 않음")
            continue
        if conn.execute("SELECT 1 FROM macro_alerts WHERE date = ? AND key = ?", (last_date, key)).fetchone():
            _log(f"{key}: {last_date} 이미 알림")
            continue
        if not res.get(1, {}).get("hit"):
            since = (date.fromisoformat(last_date) - timedelta(days=REPEAT_DAYS)).isoformat()
            if conn.execute("SELECT 1 FROM macro_alerts WHERE key = ? AND date >= ?", (key, since)).fetchone():
                _log(f"{key}: 5일 변화만 걸림 - 지난 {REPEAT_DAYS}일 안에 알린 적 있어 건너뜀")
                continue
        lines.append(build_line(name, unit, kind, last_date, values, res))
        sent_keys.append((last_date, key, json.dumps({h: round(r["ratio"], 2) for h, r in res.items()})))

    if not lines:
        _log("급변 없음 - 보내지 않음")
        return 0
    text = "\n".join(["📈 <b>환율·금리·VIX 급변</b>",
                      "평소 변화폭(지난 1년 표준편차)의 2배 이상 움직인 것만", "", *lines, "",
                      f'<a href="{SITE}">개요에서 보기</a>'])
    _log(text)
    if args.dry_run or not args.notify:
        _log("발송 안 함(dry-run 또는 --notify 없음)")
        return 0
    send_telegram(text)
    now = today.isoformat()
    for d, k, detail in sent_keys:
        conn.execute("INSERT OR IGNORE INTO macro_alerts (date, key, sent_at, detail) VALUES (?, ?, ?, ?)", (d, k, now, detail))
    conn.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
