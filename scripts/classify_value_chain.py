"""소속 기업을 테마 가치사슬 구간에 배정한다 (2026-11-05, 마스터 플랜 2단계 '가치사슬 시각화').

테마·시장마다 최신 승인 매핑 run의 소속 기업(직접·부분·간접 전부) 중 아직 분류하지 않은 기업만 모아 GPT에 한 번 묻는다.
입력은 themes.yaml value_chain의 (n) 구간 글과 기업 이름·업종(yfinance)·매핑 단계·근거 글뿐, 답은 구간 번호뿐이다(숫자를
만들지 않는다 - 원칙 2). 결과는 theme_member_segments에 쌓는다(덮어쓰지 않음). 이미 분류한 기업은 건너뛰므로 다시 돌려도
새 매핑·바뀐 구간 글만 비용이 든다.

    python scripts/classify_value_chain.py --dry-run            # 묻지 않고 대상만
    python scripts/classify_value_chain.py                      # 전체
    python scripts/classify_value_chain.py --theme-id ai_semiconductor --market KR
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.analyzers.value_chain import SYSTEM, build_prompt, chain_hash, parse_segments, validate
from src.db.data_store import get_db
from src.db.theme_segments import classified_tickers, ensure_schema, insert_segments
from src.llm import openai_json as oj

THEMES_YAML = ROOT / "config" / "themes.yaml"
OVERRIDES = ROOT / "config" / "value_chain_overrides.yaml"
PROFILES = ROOT / "frontend" / "src" / "data" / "companyProfiles.json"
ROLE = "value_chain"


def _log(msg: str) -> None:
    print(f"[value-chain] {msg}", flush=True)


def latest_members(conn, theme_id: str, market: str) -> tuple[str | None, list[dict]]:
    run = conn.execute("SELECT MAX(run_id) FROM theme_members WHERE theme_id = ? AND market = ? AND approved = 1",
                       (theme_id, market)).fetchone()
    run_id = run[0] if run else None
    if not run_id:
        return None, []
    rows = conn.execute("SELECT ticker, stage, evidence, linkage FROM theme_members "
                        "WHERE theme_id = ? AND market = ? AND run_id = ? AND approved = 1", (theme_id, market, run_id)).fetchall()
    return run_id, [{"ticker": r[0], "stage": r[1], "evidence": r[2], "linkage": r[3]} for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme-id", nargs="*", default=None)
    ap.add_argument("--market", choices=["US", "KR"], default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show-prompt", action="store_true", help="dry-run에서 보낼 프롬프트를 그대로 출력(이미 분류한 기업 포함)")
    args = ap.parse_args()

    data = yaml.safe_load(THEMES_YAML.read_text(encoding="utf-8"))
    themes = [t for t in data["themes"] if t.get("status") == "active" and (not args.theme_id or t["id"] in args.theme_id)]
    profiles = json.loads(PROFILES.read_text(encoding="utf-8")) if PROFILES.exists() else {}
    overrides = (yaml.safe_load(OVERRIDES.read_text(encoding="utf-8")) or {}) if OVERRIDES.exists() else {}
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not args.dry_run and not api_key:
        _log("OPENAI_API_KEY 미설정")
        return 1
    model = oj.model_for(ROLE)
    conn = get_db()
    ensure_schema(conn)
    now = datetime.utcnow().isoformat()
    calls = classified = failed = 0

    for t in themes:
        chain = parse_segments(t.get("value_chain"))
        if not chain["segments"]:
            _log(f"{t['id']}: value_chain에 (n) 구간 없음 - 건너뜀")
            continue
        ov_theme = overrides.get(t["id"]) or {}
        h = chain_hash(chain["segments"], model + json.dumps(ov_theme, sort_keys=True))
        labels = {s["n"]: s["label"] for s in chain["segments"]}
        for market in [m for m in (t.get("markets") or []) if not args.market or m == args.market]:
            run_id, members = latest_members(conn, t["id"], market)
            if not members:
                continue
            done = set() if args.show_prompt else classified_tickers(conn, t["id"], market, run_id, h)
            todo = [m for m in members if m["ticker"] not in done]
            if not todo:
                continue
            for m in todo:
                p = (profiles.get(market) or {}).get(m["ticker"]) or {}
                m["name"], m["industry"] = p.get("n"), p.get("i")
            ov = {str(k): int(v) for k, v in (ov_theme.get(market) or {}).items()}
            manual = [(t["id"], market, m["ticker"], run_id, h, ov[m["ticker"]], labels.get(ov[m["ticker"]]), "manual", now)
                      for m in todo if m["ticker"] in ov]
            todo = [m for m in todo if m["ticker"] not in ov]
            _log(f"{t['id']}({market}): 소속 {len(members)} 중 분류할 {len(todo)}곳 · 수동 보정 {len(manual)} · 구간 {len(labels)}개")
            if manual and not args.dry_run:
                insert_segments(conn, manual)
                classified += len(manual)
            if not todo:
                continue
            if args.dry_run:
                if args.show_prompt:
                    print(build_prompt(t.get("name_ko") or t["id"], chain, todo), flush=True)
                continue
            calls += 1
            try:
                parsed = oj.call_json(model, SYSTEM, build_prompt(t.get("name_ko") or t["id"], chain, todo),
                                      api_key=api_key, max_output_tokens=3000, temperature=0)
            except oj.OpenAICallError as e:
                failed += 1
                _log(f"  실패 {e}")
                continue
            got = validate(parsed, [m["ticker"] for m in todo], list(labels))
            insert_segments(conn, [(t["id"], market, tk, run_id, h, n, labels.get(n), model, now) for tk, n in got.items()])
            classified += len(got)
            cnt = Counter(got.values())
            _log("  " + " · ".join(f"({n}) {cnt.get(n, 0)}" for n in [*labels, 0])
                 + (f" · 답 없음 {len(todo) - len(got)}" if len(got) < len(todo) else ""))
            by_t = {m["ticker"]: m for m in todo}
            off = [f"{tk} {by_t[tk].get('name') or ''}({by_t[tk].get('linkage')})" for tk, n in got.items() if n == 0]
            if off:
                _log(f"  구간 밖(0): {', '.join(off[:15])}")
    _log(f"완료 - 호출 {calls} · 분류 {classified} · 실패 {failed} · 모델 {model}")
    conn.close()
    return 1 if failed and not classified else 0


if __name__ == "__main__":
    raise SystemExit(main())
