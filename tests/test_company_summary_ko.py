"""기업 카드 한국어 요약 뒷손질(2026-11-05)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzers.company_summary_ko import build_prompt, clean, src_hash, validate  # noqa: E402


def test_clean_drops_numeric_sentences_keeps_product_names():
    t = "마이크론은 메모리 반도체를 만든다. 1978년에 설립됐다. 직원은 48,000명이다. G9 NAND와 HBM을 공급한다."
    assert clean(t) == "마이크론은 메모리 반도체를 만든다. G9 NAND와 HBM을 공급한다."
    assert clean("매출의 30%가 서버에서 나온다.") == ""


def test_validate_and_prompt():
    got = validate({"items": [{"symbol": "MU", "ko": "메모리를 만든다."}, {"symbol": "X", "ko": "a"},
                              {"symbol": "KO", "ko": "1886년 설립."}, {"symbol": "MU", "ko": "중복"}]}, ["MU", "KO"])
    assert got == {"MU": "메모리를 만든다."}   # KO는 숫자 문장만이라 빠짐 -> 다음 실행 때 다시
    assert "[MU] Micron" in build_prompt([("MU", "Micron", "Micron makes memory.")])
    assert src_hash("a") == src_hash("a") != src_hash("b")
