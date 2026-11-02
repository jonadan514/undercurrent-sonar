// 13F 추적 운용사(2026-10-25 사용자 선택 15곳) - config/institutions.yaml과 같은 목록(화면용 이름·스타일). 바꿀 때 두 곳 같이.
export type InvestorStyle = "장기 가치" | "성장" | "롱숏" | "매크로" | "행동주의";
export const STYLE_ORDER: InvestorStyle[] = ["장기 가치", "성장", "롱숏", "매크로", "행동주의"];
export const STYLE_NOTE: Record<InvestorStyle, string> = {
  "장기 가치": "집중·오래 보유 - 새로 산 종목이 드물고 그만큼 무게가 있다",
  "성장": "5~10년을 보는 성장 기업 - 테마 레이더(AI·소프트웨어 등)와 겹친다",
  "롱숏": "13F엔 매수 쪽만 - 회전이 빨라 분기마다 출렁인다",
  "매크로": "거시 판단에 따라 크게 바뀐다 - 업종·테마 쏠림을 보는 용도",
  "행동주의": "지분을 사서 경영 개선을 요구 - 소수 종목 집중",
};
export const INVESTORS: { id: string; ko: string; person: string; en: string; style: InvestorStyle }[] = [
  { id: "berkshire", ko: "버크셔 해서웨이", person: "워런 버핏", en: "Berkshire Hathaway", style: "장기 가치" },
  { id: "baupost", ko: "바우포스트", person: "세스 클라만", en: "Baupost Group", style: "장기 가치" },
  { id: "himalaya", ko: "히말라야 캐피털", person: "리 루", en: "Himalaya Capital", style: "장기 가치" },
  { id: "akre", ko: "아크레 캐피털", person: "척 아크레", en: "Akre Capital Management", style: "장기 가치" },
  { id: "russo", ko: "가드너 루소", person: "톰 루소", en: "Gardner Russo & Quinn", style: "장기 가치" },
  { id: "baillie", ko: "베일리 기포드", person: "", en: "Baillie Gifford", style: "성장" },
  { id: "fundsmith", ko: "펀드스미스", person: "테리 스미스", en: "Fundsmith", style: "성장" },
  { id: "lonepine", ko: "론 파인 캐피털", person: "스티븐 맨델", en: "Lone Pine Capital", style: "롱숏" },
  { id: "duquesne", ko: "듀케인 패밀리 오피스", person: "스탠리 드러켄밀러", en: "Duquesne Family Office", style: "매크로" },
  { id: "appaloosa", ko: "아팔루사", person: "데이비드 테퍼", en: "Appaloosa", style: "매크로" },
  { id: "soros", ko: "소로스 펀드", person: "조지 소로스", en: "Soros Fund Management", style: "매크로" },
  { id: "pershing", ko: "퍼싱스퀘어", person: "빌 애크먼", en: "Pershing Square", style: "행동주의" },
  { id: "elliott", ko: "엘리엇", person: "폴 싱어", en: "Elliott Investment Management", style: "행동주의" },
  { id: "thirdpoint", ko: "서드 포인트", person: "댄 로브", en: "Third Point", style: "행동주의" },
  { id: "icahn", ko: "아이칸 캐피털", person: "칼 아이칸", en: "Carl Icahn", style: "행동주의" },
];
// 스타일 표시(2026-11-02, 사용자 요청: 투자 분류가 눈에 잘 안 띈다) - 색은 구분용일 뿐 좋고 나쁨이 아니다.
export const STYLE_META: Record<InvestorStyle, { emoji: string; color: string }> = {
  "장기 가치": { emoji: "🏛️", color: "#ffb020" },
  "성장": { emoji: "🌱", color: "#4ade80" },
  "롱숏": { emoji: "⚖️", color: "#6fb3b8" },
  "매크로": { emoji: "🌐", color: "#a78bfa" },
  "행동주의": { emoji: "📣", color: "#fb923c" },
};
/** "바우포스트 · 세스 클라만" - 운용사 이름 + 대표 인물(없으면 운용사만) */
export const investorFull = (i?: { ko: string; person: string } | null) => !i ? "" : i.person ? `${i.ko} · ${i.person}` : i.ko;

export const INVESTOR_BY_ID = Object.fromEntries(INVESTORS.map((i) => [i.id, i]));

export const usd = (v: number | null | undefined) => v == null ? "-" : Math.abs(v) >= 1e9 ? `$${(v / 1e9).toFixed(1)}B`
  : Math.abs(v) >= 1e6 ? `$${(v / 1e6).toFixed(0)}M` : `$${Math.round(v / 1e3).toLocaleString()}K`;
export const quarterLabel = (p: string | null | undefined) => {
  const m = /^(\d{4})-(\d{2})/.exec(p ?? "");
  return m ? `${m[1]} Q${Math.floor((Number(m[2]) - 1) / 3) + 1}` : (p ?? "-");
};
