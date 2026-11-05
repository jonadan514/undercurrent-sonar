"""가치사슬 구간 파싱·응답 검증(2026-11-05)."""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.analyzers.value_chain import build_prompt, chain_hash, parse_segments, validate  # noqa: E402

TEXT = """AI 연산에 쓰이는 반도체.
(1) AI 가속기 설계
(2) HBM 메모리
(3) 후공정 패키징
    (반도체 장비 테마와 동시 소속 허용)
편입하지 않음: OLED 장비,
범용 부품
"""


def test_parse_segments():
    c = parse_segments(TEXT)
    assert c["intro"] == "AI 연산에 쓰이는 반도체."
    assert [s["n"] for s in c["segments"]] == [1, 2, 3]
    assert c["segments"][2]["label"] == "후공정 패키징" and "동시 소속" in c["segments"][2]["detail"]
    assert c["exclude"].startswith("편입하지 않음") and "범용 부품" in c["exclude"]
    assert parse_segments(None)["segments"] == []


def test_all_active_themes_have_segments():
    data = yaml.safe_load((ROOT / "config" / "themes.yaml").read_text(encoding="utf-8"))
    for t in data["themes"]:
        if t.get("status") == "active":
            assert len(parse_segments(t.get("value_chain"))["segments"]) >= 2, t["id"]


def test_validate_and_hash():
    got = validate({"assign": [{"ticker": "MU", "segment": 2}, {"ticker": "NVDA", "segment": "1"}, {"ticker": "X", "segment": 1},
                               {"ticker": "AMD", "segment": 9}, {"ticker": "MU", "segment": 1}, {"bad": 1}]},
                   ["MU", "NVDA", "AMD", "INTC"], [1, 2, 3])
    assert got == {"MU": 2, "NVDA": 1}
    s = parse_segments(TEXT)["segments"]
    assert chain_hash(s) == chain_hash(s) and len(chain_hash(s)) == 10
    assert "MU | Micron" in build_prompt("AI 반도체", parse_segments(TEXT), [{"ticker": "MU", "name": "Micron"}])
