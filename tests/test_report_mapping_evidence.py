"""매핑 근거 품질 점검 규칙(2026-11-05)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from report_mapping_evidence import reasons_for, theme_vocab  # noqa: E402

THEME = {"keywords_ko": ["방산 수출", "K9 자주포"], "keywords_en": ["defense"], "name_ko": "방산",
         "value_chain": "(1) 지상·항공·해양 무기체계 완제품\n(3) 방산 전자·유도무기·레이더·통신"}


def test_vague_evidence_flagged():
    v = theme_vocab(THEME)
    r = reasons_for({"stage": "방산 자재", "evidence": "LIG는 방산 자재의 연구, 개발 및 제조를 통해 기여하고 있다.",
                     "linkage": "direct", "segment": 0}, v)
    assert "구간 밖" in r and "짧음" in r
    good = reasons_for({"stage": "유도무기", "evidence": "LIG넥스원은 천궁·신궁 등 유도무기와 레이더를 개발·생산해 군에 납품하는 방산 업체다.",
                        "linkage": "direct", "segment": 3}, v)
    assert good == []


def test_vague_stage_and_no_vocab():
    r = reasons_for({"stage": "Chip Manufacturer", "evidence": "This company designs and sells semiconductors for a wide range of uses globally.",
                     "linkage": "partial", "segment": None}, theme_vocab(THEME))
    assert "단계 모호" in r and "테마어 없음" in r
