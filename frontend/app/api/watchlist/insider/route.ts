import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 종목별 내부자 장내 매수(2026-10-21, scripts/collect_insider_trades.py) - 최근 180일, 공시 값 그대로.
// 수집 전이면 표가 없다 - 빈 목록으로 돌려 화면이 칸을 숨기게 한다.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const market = searchParams.get("market");
  const symbol = searchParams.get("symbol");
  if (!market || !symbol) return NextResponse.json({ error: "market, symbol 필요" }, { status: 400 });
  try {
    const rs = await getClient().execute({
      sql: `SELECT filing_id, filed_on, trade_date, owner, role, shares, price, value, plan
            FROM insider_trades WHERE market = ? AND symbol = ? AND COALESCE(trade_date, filed_on) >= date('now', '-180 days')
            ORDER BY COALESCE(trade_date, filed_on) DESC, line LIMIT 40`,
      args: [market, symbol],
    });
    return NextResponse.json({ trades: rs.rows });
  } catch {
    return NextResponse.json({ trades: [] });
  }
}
