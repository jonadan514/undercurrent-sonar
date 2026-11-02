import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 내러티브 브리프는 주간 파이프라인(scripts/generate_narratives.py)이
// 뉴스 + GPT-4o mini로 생성해 narrative_briefs 테이블에 저장한다.
// 이 라우트는 읽기 전용.
export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const market = (searchParams.get("market") ?? "US").toUpperCase();
    const symbol = (searchParams.get("symbol") ?? "").toUpperCase();
    if (!symbol) {
      return NextResponse.json({ error: "symbol 필수" }, { status: 400 });
    }

    const client = getClient();
    const res = await client.execute({
      sql: "SELECT payload, updated_at FROM narrative_briefs WHERE market = ? AND symbol = ?",
      args: [market, symbol],
    });
    const row = res.rows[0];
    if (!row) {
      return NextResponse.json({ pending: true }, { status: 404 });
    }
    const payload = JSON.parse(row[0] as string);
    return NextResponse.json({ ...payload, cached_at: row[1] as string });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "알 수 없는 오류";
    // 테이블이 아직 없으면 "생성 대기" 취급
    if (msg.includes("no such table")) {
      return NextResponse.json({ pending: true }, { status: 404 });
    }
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
