import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// Phase B에서 한국 추가 - ?market=KR로 조회(생략 시 US, 기존 호출 하위호환).
export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const market = searchParams.get("market") === "KR" ? "KR" : "US";
    const client = getClient();

    const weekRes = await client.execute({
      sql: "SELECT MAX(week_start) FROM theme_signals WHERE market = ?",
      args: [market],
    });
    const weekStart = weekRes.rows[0]?.[0] as string | null;
    if (!weekStart) {
      return NextResponse.json({ week_start: null, signals: [] });
    }

    // earn_prelim_*(잠정실적 미리보기, 2026-11-02)는 실적 잡이 처음 돌 때 붙는 열 - 아직 없으면 그 열만 빼고 다시 조회
    const query = (prelim: boolean) => client.execute({
      sql: `
        SELECT theme_id, news_count, news_baseline, news_ratio, news_arrow,
               earn_members, earn_improved, earn_insufficient, earn_ratio, earn_arrow, earn_as_of,
               earn_surprise_n, earn_surprise_beat, earn_surprise_ratio, earn_surprise_median,
               ${prelim ? "earn_prelim_quarter, earn_prelim_n, earn_prelim_beat, earn_prelim_median," : ""}
               price_median_ret, price_index_ret, price_excess, price_arrow, price_volume_ratio,
               label, member_count, mapping_run_id
        FROM theme_signals
        WHERE market = ? AND week_start = ?
      `,
      args: [market, weekStart],
    });
    const res = await query(true).catch(() => query(false));

    const signals = res.rows.map((r) => {
      const obj: Record<string, unknown> = {};
      res.columns.forEach((col, i) => { obj[col] = r[i]; });
      return obj;
    });

    return NextResponse.json({ week_start: weekStart, signals });
  } catch (err) {
    console.error("[api/radar] error:", err);
    return NextResponse.json({ week_start: null, signals: [] });
  }
}
