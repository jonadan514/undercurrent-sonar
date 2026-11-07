import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 월간 리서치 보고서(2026-11-07, monthly_reports - scripts/generate_monthly_report.py, 매달 첫 월요일).
// 같은 달을 다시 만들면 행이 하나 더 쌓이고(이력 덮어쓰기 없음, 원칙 5) 여기서는 그 달의 가장 최근 행을 준다.
// ?month=YYYY-MM 없으면 가장 최근 달. months는 고를 수 있는 달 목록(최근 먼저).
export async function GET(req: Request) {
  const want = new URL(req.url).searchParams.get("month");
  try {
    const client = getClient();
    const ms = await client.execute("SELECT month, MAX(created_at) AS c FROM monthly_reports GROUP BY month ORDER BY month DESC LIMIT 36");
    const months = ms.rows.map((r) => String(r[0]));
    const month = want && /^\d{4}-\d{2}$/.test(want) ? want : months[0];
    if (!month) return NextResponse.json({ months: [], report: null });
    const res = await client.execute({
      sql: "SELECT payload, created_at FROM monthly_reports WHERE month = ? ORDER BY created_at DESC LIMIT 1",
      args: [month],
    });
    let report = null;
    if (res.rows[0]) {
      try { report = JSON.parse(String(res.rows[0][0])); } catch { report = null; }
    }
    return NextResponse.json({ months, month, report });
  } catch (err) {
    console.error("[api/monthly-report] error:", err);
    return NextResponse.json({ months: [], report: null });
  }
}
