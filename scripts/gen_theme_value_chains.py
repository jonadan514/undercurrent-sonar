"""테마 가치사슬 구간 목록(frontend/src/data/themeValueChains.json)을 만든다 (2026-11-05).

화면이 구간 순서와 소속 기업이 없는 구간까지 보여 주려고 쓴다(분류 결과는 theme_member_segments, scripts/classify_value_chain.py).
themes.yaml의 value_chain을 바꾸면 다시 돌려 커밋한다(gen_theme_names.py와 같은 수동 갱신).

    python scripts/gen_theme_value_chains.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.analyzers.value_chain import parse_segments  # noqa: E402

OUT = ROOT / "frontend" / "src" / "data" / "themeValueChains.json"


def main() -> int:
    data = yaml.safe_load((ROOT / "config" / "themes.yaml").read_text(encoding="utf-8"))
    out = {}
    for t in data["themes"]:
        c = parse_segments(t.get("value_chain"))
        if c["segments"]:
            out[t["id"]] = [{"n": s["n"], "label": s["label"]} for s in c["segments"]]
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(out)}개 테마")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
