// 관심 표시 배지 하나로 통일(2026-10-20, 사용성 점검) - 브리핑·워치리스트 어디서든 같은 모양.
// 표시는 보는 순서를 돕는 꼬리표일 뿐 점수·추천이 아니다(원칙 1).
export type TagKey = "my" | "note" | "turnaround" | "cand" | "theme";

export const TAGS: Record<TagKey, { label: string; color: string; title: string }> = {
  my:         { label: "내 관심",   color: "#ffb020", title: "내 워치리스트에 담은 종목" },
  note:       { label: "노트",     color: "#6fb3b8", title: "관찰 노트를 남긴 종목" },
  turnaround: { label: "실적 반전", color: "#4ade80", title: "매출 3년은 정체·역성장인데 최근 1년(없으면 분기)은 성장" },
  cand:       { label: "워치",     color: "#bcb4a2", title: "이번 주 워치리스트 후보(재무 필터 통과)" },
  theme:      { label: "테마",     color: "#bcb4a2", title: "승인된 테마 소속 기업" },
};

export default function TagBadge({ tag }: { tag: string }) {
  const t = TAGS[tag as TagKey];
  if (!t) return null;
  return (
    <span title={t.title} className="inline-block whitespace-nowrap align-middle"
      style={{ fontSize: 10, fontWeight: 700, color: t.color, border: `1px solid ${t.color}66`, padding: "0 5px", borderRadius: 3, lineHeight: "16px" }}>
      {t.label}
    </span>
  );
}

export function TagBadges({ tags }: { tags: string[] }) {
  if (!tags.length) return null;
  return <span className="inline-flex gap-1 align-middle">{tags.map((t) => <TagBadge key={t} tag={t} />)}</span>;
}
