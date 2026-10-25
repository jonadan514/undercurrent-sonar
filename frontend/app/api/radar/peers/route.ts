import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 테마 동료 비교(2026-10-25) - 종목 상세에서 "이 종목이 자기 테마 안에서 어디쯤인가".
// 이 종목이 사업 소속(직접·부분)인 테마마다, 그 테마 소속 기업들의 최근 주 값으로 중앙값·가운데 절반(25~75%)을 낸다.
// 숫자는 저장된 값 그대로(theme_member_signals: 매출 YoY·영업이익률·FCF 수익률, watchlist_screening_results: ROE).
// 순위·점수는 만들지 않는다(원칙 1). 값이 있는 동료가 PEER_MIN곳 미만이면 중앙값을 내지 않는다(데이터부족, 원칙 4).
const PEER_MIN = 5;
const METRICS = ["rev_yoy", "om_now", "fcf_yield_3y", "roe"] as const;
type Metric = typeof METRICS[number];

function quantile(sorted: number[], p: number): number {
  const i = (sorted.length - 1) * p;
  const lo = Math.floor(i), hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}
const num = (v: unknown): number | null => {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbol = searchParams.get("symbol");
  const market = searchParams.get("market") === "KR" ? "KR" : "US";
  if (!symbol) return NextResponse.json({ themes: [] }, { status: 400 });
  try {
    const client = getClient();
    const own = await client.execute({
      sql: `WITH latest AS (SELECT theme_id, MAX(run_id) AS run_id FROM theme_members WHERE market = ? AND approved = 1 GROUP BY theme_id)
            SELECT tm.theme_id FROM theme_members tm JOIN latest l ON l.theme_id = tm.theme_id AND l.run_id = tm.run_id
            WHERE tm.market = ? AND tm.ticker = ? AND tm.approved = 1 AND tm.linkage IN ('direct', 'partial')`,
      args: [market, market, symbol],
    });
    const themeIds = own.rows.map((r) => String(r.theme_id));
    if (themeIds.length === 0) return NextResponse.json({ themes: [] });

    const ph = themeIds.map(() => "?").join(",");
    // 테마마다 실적 값이 들어간 가장 최근 주의 소속 기업 값(fcf 열이 아직 없는 DB면 그 열 없이 다시).
    // 주가 잡도 같은 표에 새 주 줄을 만들어서(price_ret만), 그냥 MAX(week_start)면 실적 잡이 늦거나 실패한 주엔 값이 다 빈다.
    const sqlWith = (fcf: boolean) => `
      SELECT s.theme_id, s.ticker, s.week_start, s.rev_yoy, s.om_now${fcf ? ", s.fcf_yield_3y" : ""}
      FROM theme_member_signals s
      JOIN (SELECT theme_id, MAX(week_start) AS wk FROM theme_member_signals
             WHERE market = ? AND theme_id IN (${ph}) AND (rev_yoy IS NOT NULL OR om_now IS NOT NULL) GROUP BY theme_id) w
        ON w.theme_id = s.theme_id AND w.wk = s.week_start
      WHERE s.market = ?`;
    let rows;
    try {
      rows = (await client.execute({ sql: sqlWith(true), args: [market, ...themeIds, market] })).rows;
    } catch {
      rows = (await client.execute({ sql: sqlWith(false), args: [market, ...themeIds, market] })).rows;
    }

    const tickers = Array.from(new Set(rows.map((r) => String(r.ticker))));
    const roe: Record<string, number | null> = {};
    for (let i = 0; i < tickers.length; i += 200) {
      const chunk = tickers.slice(i, i + 200);
      const rs = await client.execute({
        sql: `SELECT symbol, roe FROM watchlist_screening_results WHERE market = ? AND symbol IN (${chunk.map(() => "?").join(",")})`,
        args: [market, ...chunk],
      });
      for (const r of rs.rows) roe[String(r.symbol)] = num(r.roe);
    }

    const themes = themeIds.map((tid) => {
      const members = rows.filter((r) => String(r.theme_id) === tid);
      const value = (r: (typeof rows)[number], m: Metric): number | null =>
        m === "roe" ? roe[String(r.ticker)] ?? null : num((r as Record<string, unknown>)[m]);
      const self = members.find((r) => String(r.ticker) === symbol);
      const metrics = Object.fromEntries(METRICS.map((m) => {
        const vals = members.map((r) => value(r, m)).filter((v): v is number => v != null).sort((a, b) => a - b);
        const enough = vals.length >= PEER_MIN;
        return [m, {
          self: self ? value(self, m) : null,
          n: vals.length,
          median: enough ? quantile(vals, 0.5) : null,
          q1: enough ? quantile(vals, 0.25) : null,
          q3: enough ? quantile(vals, 0.75) : null,
        }];
      }));
      return { theme_id: tid, week: members[0] ? String(members[0].week_start) : null, members: members.length, metrics };
    }).filter((t) => t.members > 0);

    return NextResponse.json({ peer_min: PEER_MIN, themes });
  } catch (err) {
    console.error("[api/radar/peers] error:", err);
    return NextResponse.json({ themes: [] });
  }
}
