import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 테마별 소속 기업 이벤트(2026-10-21, scripts/compute_theme_events.py) - 시장별 가장 최근 실행.
// 세 축에 더하는 점수가 아니라 옆에 놓는 건수·원문 목록. 표가 없으면 빈 값 - 화면이 칸을 숨긴다.
type Row = { theme_id: unknown; counts: unknown; items: unknown };

// 최신본은 theme_events_latest(2026-10-25부터). 그 표가 아직 없거나 비면(첫 실행 전) 예전처럼 이력 표의 가장 최근 실행.
async function latestRows(market: string): Promise<{ at: string | null; rows: Row[] }> {
  const client = getClient();
  try {
    const rs = await client.execute({ sql: "SELECT theme_id, counts, items, computed_at FROM theme_events_latest WHERE market = ?", args: [market] });
    if (rs.rows.length > 0) return { at: String(rs.rows[0].computed_at), rows: rs.rows as unknown as Row[] };
  } catch { /* 표 없음 - 아래로 */ }
  // 목록이 남은 실행만(2026-10-25부터 건수만 남긴 날은 items가 '') - 최신본 표가 생기기 전 한때만 쓰는 길
  const latest = await client.execute({ sql: "SELECT MAX(computed_at) FROM theme_events WHERE market = ? AND items != ''", args: [market] });
  const at = latest.rows[0]?.[0] as string | null;
  if (!at) return { at: null, rows: [] };
  const rs = await client.execute({ sql: "SELECT theme_id, counts, items FROM theme_events WHERE market = ? AND computed_at = ?", args: [market, at] });
  return { at, rows: rs.rows as unknown as Row[] };
}

export async function GET(request: Request) {
  const market = new URL(request.url).searchParams.get("market") === "KR" ? "KR" : "US";
  try {
    const { at, rows } = await latestRows(market);
    if (!at) return NextResponse.json({ computed_at: null, themes: {} });
    const themes: Record<string, { counts: unknown; items: unknown }> = {};
    for (const r of rows) {
      try { themes[String(r.theme_id)] = { counts: JSON.parse(String(r.counts)), items: r.items ? JSON.parse(String(r.items)) : [] }; }
      catch { /* 깨진 줄은 건너뛴다 */ }
    }
    return NextResponse.json({ computed_at: at, themes });
  } catch {
    return NextResponse.json({ computed_at: null, themes: {} });
  }
}
