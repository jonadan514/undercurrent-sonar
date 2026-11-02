"""Phase A-6: 세 축 조합 라벨.

SPEC: docs/radar/SPEC_phase_a_signals.md §5

여섯 가지 정해진 조합에만 이름을 붙인다. "모든 조합에 이름을 붙이려 하지
말 것 - 억지 분류는 정보를 더하는 게 아니라 없앤다"(SPEC 원문) - 나머지는
label=None으로 두고 화면에서 화살표만 보여준다.
"""
from __future__ import annotations

UP = ("up1", "up2")

# 순서가 뚜렷한 우선순위는 없다(동시에 두 규칙에 걸리는 경우가 안 생기게
# 규칙 자체가 서로 겹치지 않게 설계돼 있음 - SPEC 표를 그대로 옮김).
_RULES: list[tuple[set[str], set[str], set[str], str]] = [
    ({"up2"}, {"flat"}, set(UP), "Early Buzz"),
    (set(UP), set(UP), set(UP), "Full Alignment"),
    ({"flat", "down"}, {"up2"}, {"flat"}, "Quiet Strength"),
    ({"up2"}, {"down"}, {"up2"}, "Overheated Buzz"),
    ({"down"}, {"down"}, {"down"}, "Full Decline"),
    ({"down"}, set(UP), {"down"}, "Quiet Recovery"),
]


def compute_label(news_arrow: str | None, earn_arrow: str | None, price_arrow: str | None) -> str | None:
    """축이 하나라도 na/None이면 라벨을 붙이지 않는다(SPEC §5) - 판정 근거가
    불완전한 상태에서 이름을 붙이면 오해를 부른다."""
    arrows = (news_arrow, earn_arrow, price_arrow)
    if any(a is None or a == "na" for a in arrows):
        return None

    for news_set, earn_set, price_set, label in _RULES:
        if news_arrow in news_set and earn_arrow in earn_set and price_arrow in price_set:
            return label
    return None


# 화면·텔레그램 표시 이름(2026-11-02, 사용자 결정). 저장 값(theme_signals.label, 관찰 노트·신호 기록)은 위 영어 이름 그대로 두고
# 보여 줄 때만 바꾼다 - 이력(원칙 5)과 비교 코드가 깨지지 않게. 프론트 src/lib/labelNames.ts와 같은 표.
LABEL_DISPLAY = {
    "Quiet Strength": "Hidden Strength · 숨은 강세",
    "Quiet Recovery": "Hidden Recovery · 숨은 회복",
    "Early Buzz": "Early Hype · 뉴스 선행",
    "Overheated Buzz": "Overhyped · 기대 과열",
    "Full Alignment": "Broad Rally · 동반 상승",
    "Full Decline": "Broad Decline · 동반 하락",
}


def label_display(label: str | None) -> str:
    return LABEL_DISPLAY.get(label or "", label or "")
