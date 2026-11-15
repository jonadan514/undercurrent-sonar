import { NextResponse } from "next/server";
import profiles from "@/src/data/companyProfiles.json";
import { KR_STOCK_NAMES } from "@/src/lib/krStockNames";

// 종목 찾기(2026-11-15, 사용자: 사용성 C) - 메뉴 검색창. 회사 정보 파일(미국·한국)과 한국 종목 이름표에서 이름·코드로 찾는다.
// 순서는 맞는 정도로만(코드 일치 → 코드 앞부분 → 이름 앞부분 → 이름 안) - 점수·추천이 아니다. 새 조회 없음.
type Profile = { n?: string };
const PROFILES = profiles as unknown as Record<"US" | "KR", Record<string, Profile>>;
type Hit = { market: "US" | "KR"; symbol: string; name: string };

const ALL: Hit[] = (() => {
  const seen = new Set<string>();
  const out: Hit[] = [];
  for (const mk of ["US", "KR"] as const) {
    for (const [sym, p] of Object.entries(PROFILES[mk] ?? {})) {
      seen.add(`${mk}:${sym}`);
      out.push({ market: mk, symbol: sym, name: p.n || (mk === "KR" ? KR_STOCK_NAMES[sym] ?? sym : sym) });
    }
  }
  for (const [sym, n] of Object.entries(KR_STOCK_NAMES)) if (!seen.has(`KR:${sym}`)) out.push({ market: "KR", symbol: sym, name: n });
  return out;
})();

export async function GET(request: Request) {
  const q = (new URL(request.url).searchParams.get("q") ?? "").trim().toLowerCase();
  if (!q) return NextResponse.json({ items: [] });
  const rank = (h: Hit): number => {
    const s = h.symbol.toLowerCase(), n = h.name.toLowerCase();
    if (s === q) return 0;
    if (s.startsWith(q)) return 1;
    if (n.startsWith(q)) return 2;
    if (n.includes(q)) return 3;
    return 9;
  };
  const items = ALL.map((h) => [rank(h), h] as const).filter(([r]) => r < 9)
    .sort((a, b) => a[0] - b[0] || a[1].name.length - b[1].name.length).slice(0, 8).map(([, h]) => h);
  return NextResponse.json({ items });
}
