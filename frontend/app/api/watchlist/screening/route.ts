import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 후보가 아닌 종목의 트랩 필터 판정(2026-10-21) - 통과/탈락/데이터부족 3분류와 사유(watchlist_screening_results).
// 결과가 없으면(유니버스 밖이거나 아직 안 돌았음) null - 화면은 "미확인"으로, 탈락으로 단정하지 않는다(원칙 4).
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const market = searchParams.get("market");
  const symbol = searchParams.get("symbol");
  if (!market || !symbol) return NextResponse.json({ error: "market, symbol 필요" }, { status: 400 });
  try {
    const rs = await getClient().execute({
      sql: "SELECT status, piotroski, red_flags, screened_at FROM watchlist_screening_results WHERE market = ? AND symbol = ?",
      args: [market, symbol],
    });
    const r = rs.rows[0];
    if (!r) return NextResponse.json({ screening: null });
    let reasons: string[] = [];
    try { const p = JSON.parse(String(r.red_flags ?? "[]")); if (Array.isArray(p)) reasons = p.filter((x) => typeof x === "string"); } catch { /* 사유 없이 */ }
    return NextResponse.json({ screening: { status: r.status, piotroski: r.piotroski, reasons, screened_at: r.screened_at } });
  } catch {
    return NextResponse.json({ screening: null });
  }
}
