import { NextResponse } from "next/server";
import PROFILES_RAW from "@/src/data/companyProfiles.json";
import { krStockName } from "@/src/lib/krStockNames";
import { parseRss, pickContra, searchName } from "@/src/lib/contraNews";

// 기업 카드 '반대 의견·악재 기사'(2026-11-07) - 구글 뉴스 RSS 최근 60일에서 부정 낱말이 든 제목만(src/lib/contraNews.ts).
// 저장하지 않고 열 때 받는다(6시간 캐시). GPT 없음 - 제목·링크·매체·날짜 그대로.
const PROFILES = PROFILES_RAW as Record<string, Record<string, { n?: string }>>;
const DAYS = 60;

export async function GET(request: Request) {
  const raw = (new URL(request.url).searchParams.get("stock") ?? "").trim();
  const [m, ...rest] = raw.split(":");
  const market = m === "KR" ? "KR" : m === "US" ? "US" : null;
  const symbol = rest.join(":").trim().toUpperCase();
  if (!market || !symbol) return NextResponse.json({ error: "stock=US:MU 형식" }, { status: 400 });
  const name = market === "KR" ? (krStockName(symbol) || PROFILES.KR?.[symbol]?.n || symbol) : searchName(PROFILES.US?.[symbol]?.n || symbol);
  const q = market === "KR" ? `"${name}" when:${DAYS}d` : `"${name}" stock when:${DAYS}d`;
  const loc = market === "KR" ? "hl=ko&gl=KR&ceid=KR:ko" : "hl=en-US&gl=US&ceid=US:en";
  const url = `https://news.google.com/rss/search?q=${encodeURIComponent(q)}&${loc}`;
  const searchUrl = `https://news.google.com/search?q=${encodeURIComponent(market === "KR" ? `"${name}"` : `"${name}" stock`)}&${loc}`;
  try {
    const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0 (U-Sonar research)" }, next: { revalidate: 21600 } });
    if (!res.ok) return NextResponse.json({ query: name, total: null, items: [], search_url: searchUrl, error: `뉴스 응답 ${res.status}` });
    const all = parseRss(await res.text());
    return NextResponse.json({ query: name, days: DAYS, total: all.length, items: pickContra(all, market), search_url: searchUrl });
  } catch (err) {
    console.error("[api/company/news] error:", err);
    return NextResponse.json({ query: name, total: null, items: [], search_url: searchUrl, error: "뉴스를 받지 못함" });
  }
}
