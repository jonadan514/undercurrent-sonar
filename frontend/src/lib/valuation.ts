// 밸류 등급 표시 이름(2026-11-02, 사용자 결정). 저장 값(watchlist_candidates.valuation_tier, 관찰 노트 스냅샷)은
// "싼 편 / 중간 / 비싼 편" 그대로 두고 화면에서만 바꾼다 - 이력(원칙 5)과 필터 비교가 깨지지 않게.
// 같은 시장 후보 안에서 PSR 3등분한 위치일 뿐 판정·점수가 아니다(원칙 1).
export const TIER_LABEL: Record<string, string> = { "싼 편": "저밸류", "중간": "중간", "비싼 편": "고밸류" };

export function tierLabel(tier: string | null | undefined): string {
  return tier ? TIER_LABEL[tier] ?? tier : "";
}
