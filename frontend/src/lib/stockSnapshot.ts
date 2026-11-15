import { getClient } from "@/src/lib/db";

// 종목·테마 "그때 값"(2026-10-05 관찰 노트에서 시작, 2026-11-15 검토 기록과 함께 쓰려고 옮김).
// 숫자는 전부 DB 값(그 순간 DB에 있는 최신 주간 값) - 만들어 내지 않는다(원칙 2).
type Client = ReturnType<typeof getClient>;
type Row = Record<string, unknown>;
const objects = (res: { columns: string[]; rows: unknown[][] }): Row[] =>
  res.rows.map((r) => Object.fromEntries(res.columns.map((c, i) => [c, r[i]])));

export async function themeSnapshot(client: Client, themeId: string, market: string): Promise<Row | null> {
  const res = await client.execute({
    sql: `SELECT week_start, news_arrow, earn_arrow, price_arrow, label, price_excess, news_count, earn_ratio
          FROM theme_signals WHERE theme_id = ? AND market = ? ORDER BY week_start DESC LIMIT 1`,
    args: [themeId, market],
  });
  return objects(res as never)[0] ?? null;
}

export async function stockSnapshot(client: Client, ticker: string, market: string): Promise<Row> {
  const snap: Row = { themes: [], price_ret_4w: null, earn_status: null, rev_yoy: null,
                      piotroski: null, valuation_tier: null, growth_tier: null, week_start: null };
  const tRes = await client.execute({
    sql: `WITH latest_runs AS (SELECT theme_id, MAX(run_id) AS run_id FROM theme_members
                                WHERE market = ? AND approved = 1 GROUP BY theme_id)
          SELECT tm.theme_id FROM theme_members tm
          JOIN latest_runs lr ON lr.theme_id = tm.theme_id AND lr.run_id = tm.run_id
          WHERE tm.ticker = ? AND tm.market = ? AND tm.approved = 1 AND tm.linkage IN ('direct', 'partial')`,
    args: [market, ticker, market],
  });
  const themes: Row[] = [];
  for (const r of tRes.rows) {
    const s = await themeSnapshot(client, r[0] as string, market);
    if (s) themes.push({ theme_id: r[0], news_arrow: s.news_arrow, earn_arrow: s.earn_arrow, price_arrow: s.price_arrow, label: s.label });
  }
  snap.themes = themes;
  try {
    const m = objects(await client.execute({
      sql: `SELECT week_start, price_ret, earn_status, rev_yoy FROM theme_member_signals
            WHERE ticker = ? AND market = ? ORDER BY week_start DESC LIMIT 1`,
      args: [ticker, market],
    }) as never)[0];
    if (m) Object.assign(snap, { week_start: m.week_start, price_ret_4w: m.price_ret, earn_status: m.earn_status, rev_yoy: m.rev_yoy });
  } catch { /* 표 없음 */ }
  try {
    const w = objects(await client.execute({
      sql: "SELECT piotroski, valuation_tier, growth_tier FROM watchlist_candidates WHERE market = ? AND symbol = ?",
      args: [market, ticker],
    }) as never)[0];
    if (w) Object.assign(snap, w);
  } catch { /* 열 없음 */ }
  return snap;
}

