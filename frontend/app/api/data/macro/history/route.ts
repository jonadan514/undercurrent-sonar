import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 매크로 지표 일별 종가 1년치(macro_history, src/analyzers/macro_snapshot.py - 2026-10-17).
// { 지표키: [[날짜, 값], ...] } 날짜 오름차순. 표가 없으면 빈 객체 - 화면은 추세선 없이 값만 보여준다.
export async function GET() {
  try {
    const client = getClient();
    const result = await client.execute(
      "SELECT date, key, value FROM macro_history WHERE date >= date('now', '-370 days') ORDER BY date"
    );
    const out: Record<string, [string, number][]> = {};
    for (const r of result.rows) {
      const key = r[1] as string;
      (out[key] ??= []).push([r[0] as string, Number(r[2])]);
    }
    return NextResponse.json(out);
  } catch {
    return NextResponse.json({});
  }
}
