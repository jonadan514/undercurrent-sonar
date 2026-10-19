import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";
import { recentSurprises } from "@/src/lib/surprises";
import { infoFacts } from "@/src/lib/infoFacts";

export const dynamic = "force-dynamic";

const BASE_COLS = `
  SELECT market, symbol, name, market_cap, sector,
         piotroski, debt_ratio, interest_coverage,
         cfo_positive_count, red_flags, regime_fit,
         roe, current_price, data_notes, screened_at`;
const VALUE_COLS = `${BASE_COLS}, psr, per, valuation_tier`;
const GROWTH_COLS = `${VALUE_COLS}, revenue_cagr_3y, revenue_yoy, op_margin_direction, growth_tier`;
// universe_source는 성장 컬럼보다도 나중에 붙었다(S&P 400 편입,
// docs/SPEC_us_universe_sp400.md). 주간 스크리닝이 한 번 돌기 전까지는 운영 표에
// 없으므로 반드시 가장 바깥 계층이어야 한다 - 아래쪽 계층에 넣으면 폴백이
// 전부 실패해서 후보가 통째로 0개로 보인다(폴백이 막으려던 바로 그 사고).
const FULL_COLS = `${GROWTH_COLS}, universe_source`;
// 분기 영업이익률 전년동기 비교(2026-10-05) - 가장 늦게 붙은 열이라 가장 바깥 계층. 다음 주간 스크리닝 전까지 운영 표에 없다.
const MARGIN_COLS = `${FULL_COLS}, op_margin_q_now, op_margin_q_change, op_margin_q_status`;
// 최근 분기 매출 전년동기 대비(2026-10-09) - 위보다도 늦게 붙은 열이라 그 바깥 계층.
const REVQ_COLS = `${MARGIN_COLS}, rev_q_yoy, rev_q_tier, rev_q_quarter`;
// 최근 4개 분기 합 대 직전 4개 분기 합(2026-10-09) - 가장 바깥 계층.
const TTM_COLS = `${REVQ_COLS}, rev_ttm_yoy, rev_ttm_tier, rev_ttm_quarter`;
// FCF 수익률(2026-10-19) - 가장 늦게 붙은 열이라 가장 바깥 계층. 상세 카드 전용(필터 없음).
const FCF_COLS = `${TTM_COLS}, fcf_yield_3y, fcf_yield_latest, fcf_negative_years, fcf_latest_year`;

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const market    = searchParams.get("market");
    const regimeFit = searchParams.get("regime_fit");
    const valuation = searchParams.get("valuation");   // "싼 편" 등, 없으면 전체
    const growth    = searchParams.get("growth");      // "성장" 등, 없으면 전체

    const client = getClient();

    const args: (string | null)[] = [];
    let where = "";
    if (market)    { where += " AND market = ?";        args.push(market); }
    if (regimeFit) { where += " AND regime_fit = ?";    args.push(regimeFit); }
    if (valuation) { where += " AND valuation_tier = ?"; args.push(valuation); }
    if (growth)    { where += " AND growth_tier = ?";    args.push(growth); }
    // 순위 없는 후보 목록 — 모멘텀/품질 점수 정렬 없음. 알파벳 순으로만 안정적 표시.
    const tail = ` FROM watchlist_candidates WHERE 1=1${where} ORDER BY market, symbol`;

    // psr/per/valuation_tier, revenue_cagr_3y 등은 나중에 붙인 컬럼이다
    // (compute_watchlist_valuation.py의 ALTER TABLE - 성장 컬럼은 밸류보다도 나중에
    // 추가됨, docs/SPEC_watchlist_growth.md). 이 화면이 그 스크립트보다 먼저
    // 배포되면 SELECT나 WHERE(필터)가 "no such column"으로 죽는데, 기존 catch가
    // 그걸 **빈 목록**으로 바꿔 버려서 후보 275종목이 0종목으로 보인다. 컬럼
    // 계층(전체 -> 성장 -> 밸류 -> 기본)을 하나씩 낮춰가며 재시도해 목록 자체는
    // 항상 뜨게 한다.
    const res = await client.execute({ sql: FCF_COLS + tail, args })
      .catch(async () => await client.execute({ sql: TTM_COLS + tail, args }))
      .catch(async () => await client.execute({ sql: REVQ_COLS + tail, args }))
      .catch(async () => await client.execute({ sql: MARGIN_COLS + tail, args }))
      .catch(async () => await client.execute({ sql: FULL_COLS + tail, args }))
      .catch(async () => await client.execute({ sql: GROWTH_COLS + tail, args })
      .catch(async () => {
        if (growth) return { rows: [], columns: [] };   // 성장 필터인데 컬럼이 없으면 결과 없음이 맞다
        return await client.execute({ sql: VALUE_COLS + tail, args })
          .catch(async () => {
            if (valuation) return { rows: [], columns: [] };   // 밸류 필터인데 컬럼이 없으면 결과 없음이 맞다
            return await client.execute({ sql: BASE_COLS + tail, args })
              .catch(() => ({ rows: [], columns: [] }));
          });
      }));

    const candidates = res.rows.map((r: any) => {
      const obj: Record<string, unknown> = {};
      (res as any).columns?.forEach((col: string, i: number) => { obj[col] = r[i]; });
      obj.red_flags = (() => { try { return JSON.parse((obj.red_flags as string) || "[]"); } catch { return []; } })();
      obj.data_notes = (() => { try { return JSON.parse((obj.data_notes as string) || "{}"); } catch { return {}; } })();
      return obj;
    });

    // 이번 회차에 새로 통과한 종목 표시 (watchlist_candidate_history 비교).
    //
    // 후보가 275종목이라 목록만으로는 "이번 주에 뭐가 달라졌는지"를 알 수 없었다.
    // 주간 브리핑(generate_weekly_briefing.py)이 같은 계산을 이미 하고 있었지만 그
    // 결과가 텔레그램과 /briefing 화면에만 가고 정작 이 목록에는 오지 않았다.
    //
    // 스냅샷(watchlist_weekly_snapshots) 대신 이력 테이블을 쓰는 이유: 스냅샷은
    // 브리핑이 돌 때 "이번 주 것"까지 덮어써서, 브리핑이 먼저 돌면 신규가 0으로
    // 보인다. 이력 테이블은 스크리닝이 회차마다 쌓고 지우지 않아 순서에 안 흔들린다.
    //
    // 직전 회차가 아예 없으면(첫 스크리닝) is_new를 true가 아니라 **null**로 둔다 -
    // 모르는 것을 "신규"로 단정하면 첫 주에 275종목이 전부 새것처럼 보인다.
    await attachNewFlags(client, candidates, market);
    await attachThemes(client, candidates, market);
    // 종목별 최근 실적 서프라이즈(최근 100일 발표만, 시장별 조회)
    for (const mkt of Array.from(new Set(candidates.map((c) => c.market as string)))) {
      const sp = await recentSurprises(client, mkt, candidates.filter((c) => c.market === mkt).map((c) => c.symbol as string));
      candidates.filter((c) => c.market === mkt).forEach((c) => { c.surprise = sp[c.symbol as string] ?? null; });
    }
    // 애널리스트 수·52주 위치 (yfinance 기업 정보, 수집 시점 기준)
    const facts = await infoFacts(client, candidates.map((c) => c.symbol as string));
    candidates.forEach((c) => { c.facts = facts[c.symbol as string] ?? null; });

    const lastScreened = (candidates[0] as any)?.screened_at ?? null;
    return NextResponse.json({ candidates, screened_at: lastScreened });
  } catch {
    return NextResponse.json({ candidates: [], screened_at: null });
  }
}

async function attachNewFlags(
  client: ReturnType<typeof getClient>,
  candidates: Record<string, unknown>[],
  market: string | null,
): Promise<void> {
  if (candidates.length === 0) return;
  try {
    const markets = market ? [market] : Array.from(new Set(candidates.map((c) => c.market as string)));

    for (const mkt of markets) {
      const dateRes = await client.execute({
        sql: `SELECT DISTINCT screened_date FROM watchlist_candidate_history
              WHERE market = ? ORDER BY screened_date DESC LIMIT 2`,
        args: [mkt],
      });
      const prevDate = dateRes.rows[1]?.[0] as string | undefined;
      const rowsOfMarket = candidates.filter((c) => c.market === mkt);

      if (!prevDate) {
        rowsOfMarket.forEach((c) => { c.is_new = null; });
        continue;
      }

      const prevRes = await client.execute({
        sql: `SELECT symbol FROM watchlist_candidate_history
              WHERE market = ? AND screened_date = ?`,
        args: [mkt, prevDate],
      });
      const prevSymbols = new Set(prevRes.rows.map((r) => r[0] as string));

      // 처음 등장인지 재진입인지 구분한다 - 둘 다 "신규"지만 의미가 다르다.
      const firstRes = await client.execute({
        sql: `SELECT symbol, MIN(screened_date) FROM watchlist_candidate_history
              WHERE market = ? GROUP BY symbol`,
        args: [mkt],
      });
      const firstSeen = new Map(firstRes.rows.map((r) => [r[0] as string, r[1] as string]));
      const latestDate = dateRes.rows[0]?.[0] as string | undefined;

      rowsOfMarket.forEach((c) => {
        const sym = c.symbol as string;
        c.is_new = !prevSymbols.has(sym);
        c.first_seen = firstSeen.get(sym) ?? null;
        c.is_reentry = c.is_new === true && firstSeen.get(sym) !== undefined
          && firstSeen.get(sym) !== latestDate;
      });
    }
  } catch {
    // 이력 조회가 실패해도 후보 목록 자체는 그대로 보여준다.
    candidates.forEach((c) => { if (c.is_new === undefined) c.is_new = null; });
  }
}


// 후보마다 소속 테마(사업 소속 direct/partial만)와 그 테마의 이번 주 레이더 라벨·최근 분기 분류를 붙인다.
// 워치리스트에서 "지금 흐름 안에 있는 종목"만 걸러 보려는 용도(2026-10-04). 시장 인식(perceived)은
// 3축 계산에서 빼는 것과 같은 이유로 넣지 않는다. 시장별로 쿼리 1-2번 - 종목마다 조회하지 않는다.
// 실패해도 목록은 그대로 뜬다(themes만 빈 배열).
async function attachThemes(
  client: ReturnType<typeof getClient>,
  candidates: Record<string, unknown>[],
  market: string | null,
): Promise<void> {
  candidates.forEach((c) => { c.themes = []; });
  if (candidates.length === 0) return;
  const markets = market ? [market] : Array.from(new Set(candidates.map((c) => c.market as string)));
  for (const mkt of markets) {
    try {
      const res = await client.execute({
        sql: `
          WITH latest_runs AS (
            SELECT theme_id, MAX(run_id) AS run_id FROM theme_members
            WHERE market = ? AND approved = 1 GROUP BY theme_id
          )
          SELECT tm.ticker, tm.theme_id, ts.label, ts.earn_arrow, ts.price_arrow
          FROM theme_members tm
          JOIN latest_runs lr ON lr.theme_id = tm.theme_id AND lr.run_id = tm.run_id
          LEFT JOIN theme_signals ts ON ts.theme_id = tm.theme_id AND ts.market = ?
            AND ts.week_start = (SELECT MAX(week_start) FROM theme_signals WHERE market = ?)
          WHERE tm.market = ? AND tm.approved = 1 AND tm.linkage IN ('direct', 'partial')
        `,
        args: [mkt, mkt, mkt, mkt],
      });
      // 최근 분기 분류(없으면 비워 둔다 - 분기 표가 아직 없어도 목록은 떠야 한다)
      const quarterly: Record<string, string | null> = {};
      try {
        const q = await client.execute({
          sql: `
            SELECT theme_id, classification FROM quarterly_theme_classification
            WHERE market = ? AND (fiscal_year * 10 + fiscal_quarter) = (
              SELECT MAX(fiscal_year * 10 + fiscal_quarter) FROM quarterly_theme_classification WHERE market = ?
            )
          `,
          args: [mkt, mkt],
        });
        q.rows.forEach((r) => { quarterly[r[0] as string] = (r[1] as string | null) ?? null; });
      } catch { /* 분기 표 없음 */ }

      // earn_arrow·price_arrow: 라벨이 없는 동안(뉴스 기준선 쌓이는 중) 화면이 "실적 ↑·주가 ↑ 아님"을 대체 기준으로 쓴다
      type T = { theme_id: string; label: string | null; quarterly: string | null; earn_arrow: string | null; price_arrow: string | null };
      const byTicker: Record<string, T[]> = {};
      res.rows.forEach((r) => {
        const t = r[0] as string, tid = r[1] as string;
        (byTicker[t] ??= []).push({ theme_id: tid, label: (r[2] as string | null) ?? null, quarterly: quarterly[tid] ?? null,
                                    earn_arrow: (r[3] as string | null) ?? null, price_arrow: (r[4] as string | null) ?? null });
      });
      candidates.filter((c) => c.market === mkt).forEach((c) => { c.themes = byTicker[c.symbol as string] ?? []; });
    } catch { /* 테마 표 조회 실패 - 빈 배열 유지 */ }
  }
}
