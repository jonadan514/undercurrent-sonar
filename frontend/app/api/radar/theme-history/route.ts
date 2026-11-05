import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";
import { recentSurprises } from "@/src/lib/surprises";
import { infoFacts } from "@/src/lib/infoFacts";
import PROFILES_RAW from "@/src/data/companyProfiles.json";

const PROFILES = PROFILES_RAW as Record<string, Record<string, { n?: string }>>;

export const dynamic = "force-dynamic";

// 테마 흐름 이력 (2026-10-05) - 테마 하나의 주별 세 축(theme_signals)과, 최근 주 소속 기업별 값
// (theme_member_signals). 세 축은 합치지 않고 그대로 돌려준다(원칙 1). 숫자는 전부 DB에 있는 값.
//
// 뉴스 수집원이 바뀐 주(src/db/theme_signals.py NEWS_SOURCE_SWITCH_WEEK) - 그 앞뒤 건수는 비교할 수 없어
// 화면이 구분선을 긋는다. 파이썬 쪽 값이 바뀌면 여기도 같이 바꿀 것.
const NEWS_SOURCE_SWITCH_WEEK: Record<string, string> = { US: "2026-09-28", KR: "2026-09-28" };
const MAX_WEEKS = 26;

type Row = Record<string, unknown>;
const toObjects = (res: { columns: string[]; rows: unknown[][] }): Row[] =>
  res.rows.map((r) => Object.fromEntries(res.columns.map((c, i) => [c, r[i]])));

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const themeId = searchParams.get("theme_id");
  if (!themeId) return NextResponse.json({ error: "theme_id 필요" }, { status: 400 });
  const market = searchParams.get("market") === "KR" ? "KR" : "US";
  const weeks = Math.min(Math.max(Number(searchParams.get("weeks")) || 12, 4), MAX_WEEKS);

  const empty = { theme_id: themeId, market, weeks: [], members: [], member_counts: null,
                  news_source_switch_week: NEWS_SOURCE_SWITCH_WEEK[market] };
  try {
    const client = getClient();

    const sigRes = await client.execute({
      sql: `
        SELECT week_start, news_count, news_baseline, news_ratio, news_arrow, news_market_ratio, news_rel_ratio,
               earn_members, earn_improved, earn_insufficient, earn_ratio, earn_arrow, earn_as_of,
               price_median_ret, price_index_ret, price_excess, price_arrow, label, member_count
        FROM theme_signals WHERE theme_id = ? AND market = ?
        ORDER BY week_start DESC LIMIT ?
      `,
      args: [themeId, market, weeks],
    });
    const weekRows = toObjects(sigRes as never).reverse();   // 오래된 주 -> 최근 주

    // 소속 구성 - 최신 승인 run 기준(레이더·워치리스트와 같은 규칙)
    let memberCounts: { business: number; perceived: number; peripheral: number } | null = null;
    const linkageByTicker: Record<string, string> = {};
    const runRes = await client.execute({
      sql: "SELECT MAX(run_id) FROM theme_members WHERE theme_id = ? AND market = ? AND approved = 1",
      args: [themeId, market],
    });
    const runId = runRes.rows[0]?.[0] as string | null;
    if (runId) {
      const mRes = await client.execute({
        sql: "SELECT ticker, linkage FROM theme_members WHERE theme_id = ? AND market = ? AND run_id = ? AND approved = 1",
        args: [themeId, market, runId],
      });
      memberCounts = { business: 0, perceived: 0, peripheral: 0 };
      mRes.rows.forEach((r) => {
        const linkage = r[1] as string;
        linkageByTicker[r[0] as string] = linkage;
        if (linkage === "perceived") memberCounts!.perceived++;
        else if (linkage === "peripheral") memberCounts!.peripheral++;
        else memberCounts!.business++;
      });
    }

    // 기업별 값 - 가장 최근에 기업별 값이 남은 주(2026-10-05 이전 주에는 없다)
    let members: Row[] = [];
    let membersWeek: string | null = null;
    try {
      const wRes = await client.execute({
        sql: "SELECT MAX(week_start) FROM theme_member_signals WHERE theme_id = ? AND market = ?",
        args: [themeId, market],
      });
      membersWeek = (wRes.rows[0]?.[0] as string | null) ?? null;
      if (membersWeek) {
        // om_*(분기 영업이익률 전년동기 비교)는 2026-10-05, prelim_*(한국 잠정실적)은 2026-11-02에 붙은 열 - 없으면 그 열만 빼고 다시 조회
        const memberSql = (withMargin: boolean, withPrelim = false) => `
            SELECT ms.ticker, ms.price_ret, ms.rev_yoy, ms.rev_quarter, ms.earn_status,
                   ${withMargin ? "ms.om_now, ms.om_change, ms.om_status," : ""}
                   ${withPrelim ? "ms.prelim_rev_yoy, ms.prelim_quarter," : ""}
                   wc.name AS wl_name, wc.valuation_tier, wc.growth_tier,
                   CASE WHEN wc.symbol IS NULL THEN 0 ELSE 1 END AS in_watchlist
            FROM theme_member_signals ms
            LEFT JOIN watchlist_candidates wc ON wc.market = ms.market AND wc.symbol = ms.ticker
            WHERE ms.theme_id = ? AND ms.market = ? AND ms.week_start = ?
          `;
        const msRes = await client.execute({ sql: memberSql(true, true), args: [themeId, market, membersWeek] })
          .catch(() => client.execute({ sql: memberSql(true), args: [themeId, market, membersWeek] }))
          .catch(() => client.execute({ sql: memberSql(false), args: [themeId, market, membersWeek] }));
        members = toObjects(msRes as never)
          // 지금 소속이 아닌 기업(그 뒤 재매핑으로 빠짐)은 빼고, 소속 구분을 붙인다
          .filter((m) => !runId || linkageByTicker[m.ticker as string] !== undefined)
          .map((m) => ({ ...m, linkage: linkageByTicker[m.ticker as string] ?? null }));
        // 종목별 최근 실적 서프라이즈(최근 100일 발표만)
        const sp = await recentSurprises(client, market, members.map((m) => m.ticker as string));
        const facts = await infoFacts(client, members.map((m) => m.ticker as string));
        // 가치사슬 구간(2026-11-05, theme_member_segments) - 최신 승인 run에서 가장 늦게 분류한 값. 표가 없거나 분류 전이면 null
        const seg: Record<string, { n: number; label: string | null }> = {};
        if (runId) {
          try {
            const sRes = await client.execute({
              sql: `SELECT ticker, segment, segment_label FROM theme_member_segments WHERE theme_id = ? AND market = ? AND run_id = ?
                    ORDER BY classified_at`,
              args: [themeId, market, runId],
            });
            sRes.rows.forEach((r) => { seg[r[0] as string] = { n: Number(r[1]), label: (r[2] as string | null) ?? null }; });
          } catch { /* 분류 표가 아직 없는 배포 시점 */ }
        }
        members = members.map((m) => ({ ...m, surprise: sp[m.ticker as string] ?? null, facts: facts[m.ticker as string] ?? null,
                                        segment: seg[m.ticker as string]?.n ?? null,
                                        // 회사 이름(2026-11-05) - 워치리스트 후보가 아니면 wl_name이 비어 티커만 보였다
                                        profile_name: PROFILES[market]?.[m.ticker as string]?.n ?? null }));
      }
    } catch {
      // theme_member_signals가 아직 없는 배포 시점 - 세 축 이력은 그대로 보여 준다
    }

    return NextResponse.json({
      theme_id: themeId,
      market,
      weeks: weekRows,
      member_counts: memberCounts,
      members,
      members_week: membersWeek,
      news_source_switch_week: NEWS_SOURCE_SWITCH_WEEK[market],
    });
  } catch (err) {
    console.error("[api/radar/theme-history] error:", err);
    return NextResponse.json(empty);
  }
}
