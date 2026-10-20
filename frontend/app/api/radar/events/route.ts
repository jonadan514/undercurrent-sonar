import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 테마별 소속 기업 이벤트(2026-10-21, scripts/compute_theme_events.py) - 시장별 가장 최근 실행.
// 세 축에 더하는 점수가 아니라 옆에 놓는 건수·원문 목록. 표가 없으면 빈 값 - 화면이 칸을 숨긴다.
export async function GET(request: Request) {
  const market = new URL(request.url).searchParams.get("market") === "KR" ? "KR" : "US";
  try {
    const client = getClient();
    const latest = await client.execute({ sql: "SELECT MAX(computed_at) FROM theme_events WHERE market = ?", args: [market] });
    const at = latest.rows[0]?.[0] as string | null;
    if (!at) return NextResponse.json({ computed_at: null, themes: {} });
    const rs = await client.execute({
      sql: "SELECT theme_id, counts, items FROM theme_events WHERE market = ? AND computed_at = ?",
      args: [market, at],
    });
    const themes: Record<string, { counts: unknown; items: unknown }> = {};
    for (const r of rs.rows) {
      try { themes[String(r.theme_id)] = { counts: JSON.parse(String(r.counts)), items: JSON.parse(String(r.items)) }; }
      catch { /* 깨진 줄은 건너뛴다 */ }
    }
    return NextResponse.json({ computed_at: at, themes });
  } catch {
    return NextResponse.json({ computed_at: null, themes: {} });
  }
}
