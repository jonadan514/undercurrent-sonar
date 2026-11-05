"""매핑 근거 글 품질 점검(읽기 전용, 2026-11-05, 사용자: 다음 작업 2번).

가치사슬 분류에서 드러났다 - 한화에어로스페이스 방산 근거가 "항공기 엔진 개발 및 생산을 통해 방산 분야에 기여", LIG넥스원이
"방산 자재의 연구, 개발 및 제조"뿐이라 GPT가 구간을 못 고르거나 실행마다 갈렸다. 다음 분기 재매핑(또는 수동 보정) 때 볼 목록을
코드 규칙만으로 뽑는다(GPT·비용 없음, 아무것도 쓰지 않음). 점수가 아니라 걸린 이유를 그대로 적는다.

걸리는 이유:
  짧음        근거 글이 MIN_LEN자 미만
  상투어      "~분야에 기여", "~산업에 속한다", "다양한 제품" 같은 말이 있고 구체적인 테마 어휘가 없음
  테마어 없음  테마 키워드·가치사슬 구간 글의 낱말이 근거·단계 어디에도 없음
  단계 모호    단계가 '제조'·'부품'·'Chip Manufacturer'처럼 어느 테마에나 붙는 말
  구간 밖      직접·부분 소속인데 가치사슬 분류가 '어느 구간에도 안 맞음'(classify_value_chain)
'구간 밖'이거나 이유가 둘 이상이면 목록에 올린다.

    python scripts/report_mapping_evidence.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.analyzers.value_chain import parse_segments
from src.db.data_store import get_db

MIN_LEN = 40
CLICHE = re.compile(r"(기여하고 있|기여한다|기여하며|분야에 (속|포함)|산업에 (속|포함)|업에 속|에 포함된다|관련 (사업|제품)을|"
                    r"다양한 (제품|솔루션|서비스)|중요한 역할|직접적으로 관여|관련이 있)")
VAGUE_STAGE = {"제조", "부품", "제품", "생산", "공급", "서비스", "제조업", "제조사", "부품 제조", "제품 제조", "기타",
               "manufacturer", "chip manufacturer", "manufacturing", "supplier", "energy provider", "provider", "products"}
LINKAGE_KO = {"direct": "직접", "partial": "부분", "peripheral": "간접", "perceived": "인식"}
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}|[가-힣]{2,}")
_STOP = {"등", "및", "사업", "제조", "설계", "기업", "업체", "회사", "관련", "전문", "주력", "핵심", "테마", "동시", "소속", "허용", "예",
         "제품", "부품", "서비스", "공급", "생산", "개발", "판매", "the", "and", "for"}


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text or "") if t.lower() not in _STOP}


def theme_vocab(t: dict) -> set[str]:
    """테마 키워드·가치사슬 구간 글의 낱말. 테마 이름 자체('방산', '조선')는 뺀다 - "방산 분야에 기여"처럼 이름만 되풀이한
    근거를 구체적이라고 보지 않으려고."""
    words = set()
    for k in (t.get("keywords_ko") or []) + (t.get("keywords_en") or []):
        words |= _tokens(k)
    for sg in parse_segments(t.get("value_chain"))["segments"]:
        words |= _tokens(sg["detail"])
    return words - _tokens(t.get("name_ko") or "") - _tokens(t.get("name_en") or "")


def reasons_for(m: dict, vocab: set[str]) -> list[str]:
    ev, stage = (m.get("evidence") or "").strip(), (m.get("stage") or "").strip()
    text = f"{ev} {stage}".lower()
    has_vocab = any(w in text for w in vocab)
    out = []
    if len(ev) < MIN_LEN:
        out.append("짧음")
    if CLICHE.search(ev) and not has_vocab:
        out.append("상투어")
    if not has_vocab:
        out.append("테마어 없음")
    if not stage or stage.lower() in VAGUE_STAGE or len(stage) <= 2:
        out.append("단계 모호")
    if m.get("linkage") in ("direct", "partial") and m.get("segment") == 0:
        out.append("구간 밖")
    return out


def main() -> int:
    data = yaml.safe_load((ROOT / "config" / "themes.yaml").read_text(encoding="utf-8"))
    profiles = json.loads((ROOT / "frontend" / "src" / "data" / "companyProfiles.json").read_text(encoding="utf-8"))
    conn = get_db()
    total, flagged, why = 0, 0, Counter()
    by_theme: list[tuple[str, str, int, int, list[str]]] = []
    for t in [x for x in data["themes"] if x.get("status") == "active"]:
        vocab = theme_vocab(t)
        for market in t.get("markets") or []:
            run = conn.execute("SELECT MAX(run_id) FROM theme_members WHERE theme_id = ? AND market = ? AND approved = 1",
                               (t["id"], market)).fetchone()
            run_id = run[0] if run else None
            if not run_id:
                continue
            rows = conn.execute("SELECT ticker, stage, evidence, linkage FROM theme_members WHERE theme_id = ? AND market = ? "
                                "AND run_id = ? AND approved = 1", (t["id"], market, run_id)).fetchall()
            seg = {}
            try:
                for tk, n in conn.execute("SELECT ticker, segment FROM theme_member_segments WHERE theme_id = ? AND market = ? "
                                          "AND run_id = ? ORDER BY classified_at", (t["id"], market, run_id)).fetchall():
                    seg[tk] = int(n)
            except Exception:  # noqa: BLE001 - 분류 표가 없으면 '구간 밖'만 빠진다
                pass
            lines = []
            for tk, stage, ev, linkage in rows:
                total += 1
                m = {"stage": stage, "evidence": ev, "linkage": linkage, "segment": seg.get(tk)}
                rs = reasons_for(m, vocab)
                if "구간 밖" in rs or len(rs) >= 2:
                    flagged += 1
                    why.update(rs)
                    name = ((profiles.get(market) or {}).get(tk) or {}).get("n") or ""
                    lines.append(f"    {tk} {name} ({LINKAGE_KO.get(linkage, linkage)}) [{', '.join(rs)}] 단계: {stage or '-'} | "
                                 f"근거: {(ev or '-')[:90]}")
            by_theme.append((t["id"], market, len(rows), len(lines), lines))
    print(f"[evidence] 소속 기업 {total} 중 점검 목록 {flagged} - 이유별: " + " · ".join(f"{k} {v}" for k, v in why.most_common()))
    for tid, market, n, k, lines in sorted(by_theme, key=lambda x: (-x[3], x[0])):
        if not k:
            continue
        print(f"\n== {tid}({market}) 소속 {n} 중 {k}")
        print("\n".join(lines))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
