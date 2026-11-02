import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 소속 기업 상세 (SPEC §6.4) - theme_id 하나의 최신 승인 매핑을 반환.
// 다른 테마에도 걸린 기업은 other_themes에 그 테마 id들을 담아 함께 표시("동시 소속이 정보다").
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const themeId = searchParams.get("theme_id");
  if (!themeId) {
    return NextResponse.json({ members: [] }, { status: 400 });
  }

  try {
    const market = searchParams.get("market") === "KR" ? "KR" : "US";
    const client = getClient();

    // SPEC §5 - "최신 run_id + approved=1"
    const runRes = await client.execute({
      sql: "SELECT MAX(run_id) FROM theme_members WHERE theme_id = ? AND market = ? AND approved = 1",
      args: [themeId, market],
    });
    const runId = runRes.rows[0]?.[0] as string | null;
    if (!runId) {
      return NextResponse.json({ members: [] });
    }

    const res = await client.execute({
      sql: `
        SELECT ticker, stage, evidence, linkage, confidence, flagged
        FROM theme_members
        WHERE theme_id = ? AND market = ? AND run_id = ? AND approved = 1
        ORDER BY CASE linkage WHEN 'direct' THEN 0 WHEN 'partial' THEN 1 WHEN 'peripheral' THEN 2 ELSE 3 END, ticker
      `,
      args: [themeId, market, runId],
    });
    const members = res.rows.map((r) => {
      const obj: Record<string, unknown> = {};
      res.columns.forEach((col, i) => { obj[col] = r[i]; });
      return obj;
    }) as { ticker: string; stage: string | null; evidence: string | null; linkage: string; confidence: string; flagged: number }[];

    const tickers = members.map((m) => m.ticker);
    // 동시 소속은 각 테마의 "최신 승인 run"만 본다(이 테마 목록과 같은 기준). 예전에는
    // approved=1 전체를 봐서, 재매핑으로 빠진 소속이 과거 승인분 때문에 계속 "~에도 소속"으로 떴다.
    // 시장 인식(perceived)은 사업 소속이 아니라서 따로 돌려준다 - 화면에서 구분해 표시한다.
    const crossByTicker: Record<string, string[]> = {};
    const perceivedByTicker: Record<string, string[]> = {};
    if (tickers.length > 0) {
      const placeholders = tickers.map(() => "?").join(",");
      const crossRes = await client.execute({
        sql: `
          WITH latest_runs AS (
            SELECT theme_id, MAX(run_id) AS run_id FROM theme_members
            WHERE market = ? AND approved = 1 GROUP BY theme_id
          )
          SELECT tm.ticker, tm.theme_id, tm.linkage FROM theme_members tm
          JOIN latest_runs lr ON lr.theme_id = tm.theme_id AND lr.run_id = tm.run_id
          WHERE tm.ticker IN (${placeholders}) AND tm.market = ? AND tm.approved = 1 AND tm.theme_id != ?
        `,
        args: [market, ...tickers, market, themeId],
      });
      crossRes.rows.forEach((r) => {
        const ticker = r[0] as string;
        const otherTheme = r[1] as string;
        const target = (r[2] as string) === "perceived" ? perceivedByTicker : crossByTicker;
        if (!target[ticker]) target[ticker] = [];
        if (!target[ticker].includes(otherTheme)) target[ticker].push(otherTheme);
      });
    }

    // 재무 판정 - watchlist_screening_results에 통과/탈락/데이터 부족 3분류가
    // 사유와 함께 남는다(SPEC_fundamentals_cache.md §4). 이 테이블이 생기기 전에는
    // 통과 종목만 담는 watchlist_candidates만 있어서, 화면에 안 보이는 종목이
    // 탈락인지 데이터 부족인지 구분할 수 없어 전부 "미확인"으로 표시했었다.
    // 이 테이블에도 없으면(아직 스크리닝 대상이 아니었던 종목) 그때만 "미확인".
    type Fin = { status: string; piotroski: number | null; reasons: string[] };
    const financeByTicker: Record<string, Fin> = {};
    if (tickers.length > 0) {
      const placeholders = tickers.map(() => "?").join(",");
      try {
        const financeRes = await client.execute({
          sql: `SELECT symbol, status, piotroski, red_flags FROM watchlist_screening_results
                WHERE market = ? AND symbol IN (${placeholders})`,
          args: [market, ...tickers],
        });
        financeRes.rows.forEach((r) => {
          let reasons: string[] = [];
          try {
            const parsed = JSON.parse((r[3] as string) || "[]");
            if (Array.isArray(parsed)) reasons = parsed.filter((x) => typeof x === "string");
          } catch {}
          financeByTicker[r[0] as string] = {
            status: (r[1] as string) || "unknown",
            piotroski: r[2] as number | null,
            reasons,
          };
        });
      } catch {
        // 이 테이블이 아직 없는 배포 시점에도 소속 기업 목록 자체는 보여준다
      }
    }

    const enriched = members.map((m) => ({
      ...m,
      other_themes: crossByTicker[m.ticker] ?? [],
      other_perceived: perceivedByTicker[m.ticker] ?? [],
      finance: financeByTicker[m.ticker]
        ? {
            status: financeByTicker[m.ticker].status,
            piotroski: financeByTicker[m.ticker].piotroski,
            reasons: financeByTicker[m.ticker].reasons,
          }
        : { status: "unknown", piotroski: null, reasons: [] as string[] },
    }));
    return NextResponse.json({ members: enriched });
  } catch (err) {
    console.error("[api/radar/members] error:", err);
    return NextResponse.json({ members: [] });
  }
}
