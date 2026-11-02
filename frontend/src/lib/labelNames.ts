// 테마 레이더 라벨 표시 이름(2026-11-02, 사용자 결정 - 영어+한글 짝). 저장 값(theme_signals.label)은 예전 영어 이름 그대로 두고
// 화면에서만 바꾼다 - 이력·비교 코드(BADGE_STYLE 키 등)가 깨지지 않게. 백엔드 src/analyzers/theme_labels.py LABEL_DISPLAY와 같은 표.
// (처음 영어 라벨 옆 한글은 2026-10-20 사용성 점검 때 붙였다)
export const LABEL_EN: Record<string, string> = {
  "Quiet Strength": "Hidden Strength",
  "Quiet Recovery": "Hidden Recovery",
  "Early Buzz": "Early Hype",
  "Overheated Buzz": "Overhyped",
  "Full Alignment": "Broad Rally",
  "Full Decline": "Broad Decline",
};
export const LABEL_KO: Record<string, string> = {
  "Quiet Strength": "숨은 강세",
  "Quiet Recovery": "숨은 회복",
  "Early Buzz": "뉴스 선행",
  "Overheated Buzz": "기대 과열",
  "Full Alignment": "동반 상승",
  "Full Decline": "동반 하락",
};

/** 저장 값 -> 표시 영어 이름(모르는 라벨은 그대로) */
export function labelEn(label: string | null | undefined): string {
  return label ? LABEL_EN[label] ?? label : "";
}

/** "Quiet Strength" -> "Hidden Strength · 숨은 강세" (모르는 라벨은 그대로) */
export function labelWithKo(label: string | null | undefined): string {
  if (!label) return "";
  const ko = LABEL_KO[label];
  return ko ? `${labelEn(label)} · ${ko}` : label;
}
