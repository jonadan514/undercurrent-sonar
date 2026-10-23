"""테마 소속 자동 점검 규칙 (src/analyzers/mapping_rules.py).

사례는 2026-10-16(미국)·10-22(한국) 수작업 정의 대조에서 실제로 뺀 소속이다. 지키는 것:
  - 규칙은 검토 후보를 내는 것이지 판정이 아니다 - 같은 종목도 다른 테마에서는 걸리지 않아야 한다.
  - 사업정보가 없으면 "근거 없음"이 아니라 "판단 불가"(no_profile)로 따로 낸다(원칙 4).
  - 근거 단어 파일 전체가 정규식으로 읽힌다(잘못된 이스케이프가 섞이면 점검이 통째로 죽는다).
네트워크·DB를 타지 않는다.
"""
from __future__ import annotations

import yaml

from src.analyzers.mapping_rules import (KEYWORDS_YAML, check_member, holding_conflict,
                                         load_keyword_patterns, support_conflict, utility_conflict)

PATTERNS = load_keyword_patterns()


def codes(theme, ticker, name, profiles, peers=()):
    return [c for c, _ in check_member(theme, ticker, name, profiles, list(peers), PATTERNS)]


# ── 지주사 ────────────────────────────────────────────────────────────────

def test_홀딩스는_같은_테마에_사업회사가_있으면_걸린다():
    assert holding_conflict("농심홀딩스", ["농심", "오뚜기"]) == "농심"
    assert holding_conflict("아모레퍼시픽홀딩스", ["아모레퍼시픽", "코스맥스"]) == "아모레퍼시픽"


def test_이름에_홀딩스가_없어도_자회사_이름이_이어지면_걸린다():
    assert holding_conflict("대웅", ["대웅제약", "한미약품"]) == "대웅제약"
    assert holding_conflict("넥센", ["넥센타이어", "금호타이어"]) == "넥센타이어"


def test_사업회사_쪽은_걸리지_않는다():
    """농심은 농심홀딩스가 같은 테마에 있어도 지주사가 아니다(방향이 반대)."""
    assert holding_conflict("농심", ["농심홀딩스"]) is None


def test_같은_테마에_자회사가_없으면_걸리지_않는다():
    assert holding_conflict("농심홀딩스", ["오뚜기", "삼양식품"]) is None


# ── 규제 전력회사 ───────────────────────────────────────────────────────────

def test_규제_전력회사는_에너지_테마에서_걸린다():
    assert utility_conflict("power_grid", "Utilities - Regulated Electric")
    assert utility_conflict("lng_gas", "Utilities - Diversified")


def test_도시가스사는_가스_테마에서만_허용():
    """정의 (1)이 도시가스사를 편입한다 - 같은 업종이 전력망에서는 걸린다."""
    assert utility_conflict("lng_gas", "Utilities - Regulated Gas") is None
    assert utility_conflict("power_grid", "Utilities - Regulated Gas")


def test_에너지_테마가_아니면_규제_전력회사도_걸리지_않는다():
    assert utility_conflict("defense", "Utilities - Regulated Electric") is None


# ── 사업정보 근거 ───────────────────────────────────────────────────────────

def test_사업정보에_테마_근거가_없으면_걸린다():
    """효성중공업을 전선·케이블에 - 사업정보는 변압기·차단기뿐(2026-10-22 제외)."""
    prof = {"industry": "Electrical Equipment & Parts",
            "summary_long": "manufactures transformers, circuit breakers and switchgear"}
    assert support_conflict("cable_wire", prof, PATTERNS) == "support"
    assert support_conflict("power_grid", prof, PATTERNS) is None


def test_반도체_한_단어로는_장비_테마_근거가_안_된다():
    """칩 설계사(NVDA 등)는 semiconductor라는 말만 있다 - 정의의 '팹리스 칩 설계사' 제외 항목."""
    chip = {"industry": "Semiconductors", "summary_long": "designs semiconductor chips for data centers"}
    tool = {"industry": "Semiconductor Equipment & Materials",
            "summary_long": "manufactures wafer deposition and etch systems"}
    assert support_conflict("semi_equipment", chip, PATTERNS) == "support"
    assert support_conflict("semi_equipment", tool, PATTERNS) is None


def test_한글_공시_요약도_읽는다():
    prof = {"industry": "전기장비 제조업", "summary_long": "당사는 해저케이블과 지중케이블을 제조합니다."}
    assert support_conflict("cable_wire", prof, PATTERNS) is None


def test_사업정보가_없으면_판단_불가로_따로():
    assert support_conflict("cable_wire", None, PATTERNS) == "no_profile"
    assert support_conflict("cable_wire", {"industry": "", "summary_long": ""}, PATTERNS) == "no_profile"


# ── 종합 ────────────────────────────────────────────────────────────────────

def test_보험사가_2차전지에_들어가면_업종_규칙에_걸린다():
    profiles = {"001450": {"industry": "Insurance - Property & Casualty", "summary_long": "battery"}}
    assert "industry" in codes("battery", "001450", "현대해상", profiles)


def test_정상_소속은_아무것도_걸리지_않는다():
    profiles = {"103590": {"industry": "Electrical Equipment & Parts",
                           "summary_long": "일진전기는 초고압 전력 케이블과 변압기를 제조한다"}}
    assert codes("cable_wire", "103590", "일진전기", profiles, peers=["일진전기", "대한전선"]) == []


def test_근거_단어_파일의_모든_테마가_정규식으로_읽힌다():
    raw = yaml.safe_load(KEYWORDS_YAML.read_text(encoding="utf-8"))
    assert set(PATTERNS) == set(raw)
    themes = yaml.safe_load((KEYWORDS_YAML.parent / "themes.yaml").read_text(encoding="utf-8"))["themes"]
    active = {t["id"] for t in themes if t.get("status") == "active"}
    assert active <= set(PATTERNS), f"근거 단어가 없는 활성 테마: {sorted(active - set(PATTERNS))}"
