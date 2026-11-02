// 분기 리서치 4칸 분류 표시 이름(2026-11-02, 사용자 결정 - 테마 레이더 발견 단계와 같은 말로 영어+한글 짝).
// 저장 값(quarterly_theme_classification.classification)은 "조용한 변화" 등 예전 이름 그대로 두고 화면에서만 바꾼다 -
// 이력(원칙 5)과 필터·비교 코드가 깨지지 않게.
export const CLASS_EN: Record<string, string> = {
  "조용한 변화": "Hidden", "확인된 변화": "Confirmed", "기대 선행": "Hype", "관심 밖": "Quiet",
};
export const CLASS_KO: Record<string, string> = {
  "조용한 변화": "숨은 개선", "확인된 변화": "확인된 개선", "기대 선행": "뉴스 선행", "관심 밖": "변화 없음",
};

/** "조용한 변화" -> "Hidden · 숨은 개선" (모르는 값은 그대로) */
export function classLabel(c: string | null | undefined): string {
  if (!c) return "";
  return CLASS_EN[c] ? `${CLASS_EN[c]} · ${CLASS_KO[c]}` : c;
}

/** 짧게 한글만 - 좁은 자리(지난 분기 → 이번 분기) */
export function classKo(c: string | null | undefined): string {
  return c ? CLASS_KO[c] ?? c : "";
}
