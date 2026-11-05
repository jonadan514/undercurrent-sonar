"""기업 카드 사업 요약을 한국어로 옮긴다 (2026-11-05, 사용자 결정 - gpt-4o-mini).

frontend/src/data/companyProfiles.json(yfinance 영문 원문, gen_company_profiles.py가 만든다)에서 아직 옮기지 않은 원문만 모아
BATCH개씩 한 번에 묻는다. 결과는 company_summaries_ko에 쌓는다(덮어쓰지 않음). 이미 옮긴 원문은 건너뛰어, 다시 돌려도
새 종목·바뀐 원문만 비용이 든다. 처음 한 번(약 1,600종목) 약 0.3달러.

    python scripts/gen_company_summaries_ko.py --dry-run
    python scripts/gen_company_summaries_ko.py --limit 30        # 시험
    python scripts/gen_company_summaries_ko.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.analyzers.company_summary_ko import SYSTEM, build_prompt, src_hash, validate
from src.db.company_summaries import ensure_schema, existing_keys, insert_summaries
from src.db.data_store import get_db
from src.llm import openai_json as oj

PROFILES = ROOT / "frontend" / "src" / "data" / "companyProfiles.json"
ROLE = "company_summary_ko"
BATCH = 12


def _log(msg: str) -> None:
    print(f"[summary-ko] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="이만큼만(시험)")
    ap.add_argument("--market", choices=["US", "KR"], default=None)
    args = ap.parse_args()

    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    conn = get_db()
    ensure_schema(conn)
    have = existing_keys(conn)
    todo = [(mk, sym, p.get("n") or sym, p["d"], src_hash(p["d"]))
            for mk in ("US", "KR") if not args.market or mk == args.market
            for sym, p in sorted((profiles.get(mk) or {}).items()) if p.get("d")]
    todo = [t for t in todo if (t[0], t[1], t[4]) not in have]
    if args.limit:
        todo = todo[:args.limit]
    _log(f"옮길 원문 {len(todo)}건 (이미 있음 {len(have)}) · {BATCH}개씩 {-(-len(todo) // BATCH)}회 호출")
    if args.dry_run or not todo:
        return 0
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        _log("OPENAI_API_KEY 미설정")
        return 1
    model = oj.model_for(ROLE)
    saved = failed = missing = 0
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        try:
            parsed = oj.call_json(model, SYSTEM, build_prompt([(t[1], t[2], t[3]) for t in chunk]),
                                  api_key=api_key, max_output_tokens=4000, temperature=0.2)
        except oj.OpenAICallError as e:
            failed += 1
            _log(f"  {i // BATCH + 1}회 실패 {e}")
            continue
        got = validate(parsed, [t[1] for t in chunk])
        now = datetime.utcnow().isoformat()
        insert_summaries(conn, [(t[0], t[1], t[4], got[t[1]], model, now) for t in chunk if t[1] in got])
        saved += len(got)
        missing += len(chunk) - len(got)
        if i == 0:
            for t in chunk[:3]:
                _log(f"  예) {t[0]}:{t[1]} {got.get(t[1], '(없음)')}")
        if (i // BATCH) % 20 == 19:
            _log(f"  진행 {i + len(chunk)}/{len(todo)} 저장 {saved}")
    _log(f"완료 - 저장 {saved} · 답 없음 {missing} · 호출 실패 {failed} · 모델 {model}")
    conn.close()
    return 1 if failed and not saved else 0


if __name__ == "__main__":
    raise SystemExit(main())
