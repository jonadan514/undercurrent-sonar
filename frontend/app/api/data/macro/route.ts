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
    // 이번 수집에서 한 지표만 빠진 날(yfinance가 그 종목만 못 받음 - 2026-11-07 달러인덱스)엔 macro_history의 마지막 값으로 채우고
    // 그 날짜를 as_of로 붙인다. 화면이 '-'로 비지 않게 - 값은 실제로 받았던 종가 그대로(새로 만들지 않음).
    try {
      const missing = Object.entries(snap.items ?? {}).filter(([, v]) => (v as { value: unknown }).value == null).map(([k]) => k);
      for (const k of missing) {
        const h = await client.execute({ sql: "SELECT date, value FROM macro_history WHERE key = ? ORDER BY date DESC LIMIT 6", args: [k] });
        if (!h.rows.length) continue;
        const v = h.rows.map((r) => Number(r[1]));
        snap.items[k] = { ...snap.items[k], value: v[0], chg_1d: v.length > 1 ? +(v[0] - v[1]).toFixed(4) : null,
                          chg_1w: v.length > 5 ? +(v[0] - v[5]).toFixed(4) : null, as_of: h.rows[0][0] };
      }
    } catch { /* macro_history 없음 */ }
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
