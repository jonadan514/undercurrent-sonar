import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 내 관심·노트 종목 지금 목록 + 차트 상태(2026-11-21, 사용자: 브리핑에서 관심 기업을 더 돋보이게).
// 주간 브리핑 맨 위 ⭐ 칸이 이번 주 브리핑의 '생긴 일'과 합쳐 보여 준다. 차트 값은 stock_price_facts(평일 밤) 그대로 - 판정 아님.
type Row = Record<string, unknown>;
const objects = (res: { columns: string[]; rows: unknown[][] }): Row[] =>
  res.rows.map((r) => Object.fromEntries(res.columns.map((c, i) => [c, r[i]])));
const num = (v: unknown) => (v == null ? null : Number(v));

export async function GET() {
  try {
    const client = getClient();
    const mine = new Map<string, { market: string; symbol: string; name: string | null; tags: string[] }>();
    const add = (m: unknown, s: unknown, name: unknown, tag: string) => {
      if (!m || !s) return;
      const k = `${m}:${String(s).toUpperCase()}`;
      const cur = mine.get(k) ?? { market: String(m), symbol: String(s).toUpperCase(), name: null, tags: [] };
      if (!cur.tags.includes(tag)) cur.tags.push(tag);
      if (!cur.name && name) cur.name = String(name);
      mine.set(k, cur);
    };
    try {
      for (const r of objects(await client.execute("SELECT market, symbol, name FROM my_watchlist") as never)) add(r.market, r.symbol, r.name, "my");
    } catch { /* 표 없음 */ }
    try {
      for (const r of objects(await client.execute(
        "SELECT DISTINCT market, ticker FROM observations WHERE kind = 'stock' AND ticker IS NOT NULL") as never)) add(r.market, r.ticker, null, "note");
    } catch { /* 표 없음 */ }
    const facts: Record<string, Row> = {};
    if (mine.size) {
      try {
        for (const r of objects(await client.execute(
          "SELECT market, symbol, as_of, ret_1m, pos_52w, above_ma200 FROM stock_price_facts") as never)) {
          const k = `${r.market}:${r.symbol}`;
          if (mine.has(k)) facts[k] = { as_of: r.as_of, ret_1m: num(r.ret_1m), pos_52w: num(r.pos_52w),
                                        above_ma200: r.above_ma200 == null ? null : Number(r.above_ma200) === 1 };
        }
      } catch { /* 표 없음 */ }
    }
    const items = [...mine.entries()].map(([k, v]) => ({ ...v, facts: facts[k] ?? null }))
      .sort((a, b) => Number(!a.tags.includes("my")) - Number(!b.tags.includes("my")) || a.symbol.localeCompare(b.symbol));
    return NextResponse.json({ items });
  } catch (err) {
    console.error("[api/mine] error:", err);
    return NextResponse.json({ items: [] });
  }
}
