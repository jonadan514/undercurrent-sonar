import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 시장 환경(레짐) 주간 이력(2026-11-07, market_regime_weekly - scripts/compute_market_regime.py). 시장마다 최근 WEEKS주.
// 축마다 수준·방향을 따로 주고, 정해진 조합 이름만 붙인다 - 종합 점수·등급 없음(원칙 1).
const WEEKS = 12;

export async function GET() {
  try {
    const client = getClient();
    const res = await client.execute({
      sql: "SELECT week, market, as_of, payload FROM market_regime_weekly ORDER BY week DESC LIMIT ?",
      args: [WEEKS * 2 + 4],
    });
    const out: Record<string, { week: string; as_of: string; axes: Record<string, unknown>; combos: unknown[]; context: Record<string, unknown> }[]> = { US: [], KR: [] };
    for (const r of res.rows) {
      const m = r[1] as string;
      if (!out[m] || out[m].length >= WEEKS) continue;
      try {
        const p = JSON.parse(String(r[3]));
        out[m].push({ week: r[0] as string, as_of: r[2] as string, axes: p.axes ?? {}, combos: p.combos ?? [], context: p.context ?? {} });
      } catch { /* 깨진 행은 건너뜀 */ }
    }
    for (const m of Object.keys(out)) out[m].reverse();   // 오래된 주 -> 최근 주
    return NextResponse.json(out);
  } catch (err) {
    console.error("[api/market-regime] error:", err);
    return NextResponse.json({ US: [], KR: [] });
  }
}
