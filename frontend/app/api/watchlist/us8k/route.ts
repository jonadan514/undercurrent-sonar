import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 미국 종목의 8-K 주요 공시(2026-10-21, scripts/collect_us_8k.py) - 최근 180일, 실적 발표(2.02)만 있는 것은 뺀다.
// 수집 전이면 표가 없다 - 빈 목록으로 돌려 화면이 칸을 숨기게 한다.
export async function GET(request: Request) {
  const symbol = new URL(request.url).searchParams.get("symbol");
  if (!symbol) return NextResponse.json({ error: "symbol 필요" }, { status: 400 });
  try {
    const rs = await getClient().execute({
      sql: `SELECT accession, filed_on, detail, warn, url FROM us_8k_filings
            WHERE symbol = ? AND filed_on >= date('now', '-180 days') AND items != '2.02'
            ORDER BY filed_on DESC LIMIT 20`,
      args: [symbol],
    });
    const filings = rs.rows.map((r) => {
      let d: { items?: { item: string; label: string; warn: boolean; excerpt?: string | null }[] } = {};
      try { d = JSON.parse(String(r.detail)); } catch { /* 깨진 줄은 항목 없이 */ }
      return { accession: r.accession, filed_on: r.filed_on, url: r.url, warn: Boolean(r.warn),
               items: (d.items ?? []).filter((i) => i.item !== "2.02") };
    });
    return NextResponse.json({ filings });
  } catch {
    return NextResponse.json({ filings: [] });
  }
}
