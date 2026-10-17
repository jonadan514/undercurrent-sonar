import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const client = getClient();
    const result = await client.execute(
      "SELECT payload FROM macro_snapshot ORDER BY id DESC LIMIT 1"
    );
    const row = result.rows[0];
    if (!row) return NextResponse.json(null);
    const snap = JSON.parse(row[0] as string);
    // 국고채 3년(kr_rates, pykrx - 2026-10-17)을 같은 카드 모양으로 붙인다. 표가 없으면 빼고 그대로.
    try {
      const kr = await client.execute("SELECT date, value FROM kr_rates WHERE key = 'kr3y' ORDER BY date DESC LIMIT 12");
      // 휴장일에 직전 값이 그대로 들어온 행은 하나로(브리핑 get_kr_rate_week와 같은 처리)
      const vals = kr.rows.map((r) => Number(r[1])).filter((v, i, a) => i === 0 || v !== a[i - 1]);
      if (vals.length) {
        snap.items = snap.items ?? {};
        snap.items.kr3y = {
          value: vals[0], chg_1d: vals.length > 1 ? +(vals[0] - vals[1]).toFixed(4) : null,
          chg_1w: vals.length > 5 ? +(vals[0] - vals[5]).toFixed(4) : null,
          label: "국고채 3년", unit: "%", as_of: kr.rows[0][0],
        };
      }
    } catch { /* kr_rates 없음 */ }
    return NextResponse.json(snap);
  } catch {
    return NextResponse.json(null);
  }
}
