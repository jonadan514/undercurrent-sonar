// 테마 레이더 라벨의 짧은 한글 이름(2026-10-20, 사용성 점검) - 영어 라벨은 그대로 두고 옆에 붙인다.
export const LABEL_KO: Record<string, string> = {
  "Quiet Strength": "조용한 강세",
  "Quiet Recovery": "조용한 회복",
  "Early Buzz": "이른 관심",
  "Overheated Buzz": "과열된 관심",
  "Full Alignment": "삼박자 상승",
  "Full Decline": "삼박자 하락",
};

/** "Quiet Strength" -> "Quiet Strength · 조용한 강세" (모르는 라벨은 그대로) */
export function labelWithKo(label: string | null | undefined): string {
  if (!label) return "";
  const ko = LABEL_KO[label];
  return ko ? `${label} · ${ko}` : label;
}
