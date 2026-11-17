import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 분기 4칸 분류 목록 (docs/SPEC_quarterly_screen.md 4-1).
// ?market=KR로 조회(생략 시 US, /api/radar와 같은 관례).

// Turso HTTP 프로토콜(Python 백엔드 쪽)은 INTEGER를 문자열로 돌려주는 함정이 있었다
// (docs/SPEC_quarterly_screen.md 4-3). @libsql/client(이 라우트가 쓰는 JS 클라이언트)는
// 자체적으로 숫자 타입을 돌려주지만, 혹시 문자열이 섞여 와도 깨지지 않도록 여기서
// 한 번 더 안전하게 변환한다. **null을 0으로 만들면 절대 안 된다** - 0(꺼짐/적음)과
// null(데이터 부족)은 이 화면에서 의미가 다르다.
function toNum(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
}
function toBool(v: unknown): boolean | null {
  if (v === null || v === undefined) return null;
  return Number(v) !== 0;
}

function previousQuarter(year: number, quarter: number): { year: number; quarter: number } {
  return quarter > 1 ? { year, quarter: quarter - 1 } : { year: year - 1, quarter: 4 };
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const market = searchParams.get("market") === "KR" ? "KR" : "US";
    const client = getClient();

    // 가장 최근 분기 - 연도·분기를 곱셈으로 합치지 않고 따로 정렬한다
    // (2025Q4가 2026Q1보다 커지는 것을 막는다).
    const latestRes = await client.execute({
      sql: `
        SELECT fiscal_year, fiscal_quarter FROM quarterly_theme_classification
        WHERE market = ?
        ORDER BY fiscal_year DESC, fiscal_quarter DESC
        LIMIT 1
      `,
      args: [market],
    });
    const latest = latestRes.rows[0];
    if (!latest) {
      return NextResponse.json({ fiscal_year: null, fiscal_quarter: null, market_reference: null, themes: [] });
    }
    const fiscalYear = toNum(latest[0])!;
    const fiscalQuarter = toNum(latest[1])!;

    const refRes = await client.execute({
      sql: `
        SELECT median_revenue_growth, sample_size FROM quarterly_market_reference
        WHERE market = ? AND fiscal_year = ? AND fiscal_quarter = ?
      `,
      args: [market, fiscalYear, fiscalQuarter],
    });
    const refRow = refRes.rows[0];
    const marketReference = refRow
      ? { median_revenue_growth: toNum(refRow[0]), sample_size: toNum(refRow[1]) ?? 0 }
      : null;

    const themesRes = await client.execute({
      sql: `
        SELECT theme_id, classification, financial_on, financial_changed, financial_judged,
               financial_ratio, news_high, news_ratio, news_this_quarter, computed_at
        FROM quarterly_theme_classification
        WHERE market = ? AND fiscal_year = ? AND fiscal_quarter = ?
      `,
      args: [market, fiscalYear, fiscalQuarter],
    });

    // 직전 분기 분류 - 지금 분기와 같은 시장이라 한 번 더 조회해 theme_id로 묶는다
    // (테마마다 따로 쿼리하면 왕복이 테마 수만큼 쌓인다).
    const prev = previousQuarter(fiscalYear, fiscalQuarter);
    const prevRes = await client.execute({
      sql: `
        SELECT theme_id, classification FROM quarterly_theme_classification
        WHERE market = ? AND fiscal_year = ? AND fiscal_quarter = ?
      `,
      args: [market, prev.year, prev.quarter],
    });
    const prevByTheme: Record<string, string | null> = {};
    prevRes.rows.forEach((r) => {
      prevByTheme[r[0] as string] = (r[1] as string | null) ?? null;
    });

    // 최신 재계산(2026-11-17) - 화면용 표는 분류가 있는 행을 데이터부족으로 덮지 않아서, 그 뒤 다시 계산한 재무 숫자는
    // 이력 표(quarterly_theme_classification_history)에만 있다. 테마마다 가장 최근 줄을 따로 보낸다(표가 없으면 빈 값).
    const latestFin: Record<string, { on: boolean | null; changed: number | null; judged: number | null; news_ratio: number | null; at: string }> = {};
    try {
      const h = await client.execute({
        sql: `
          SELECT h.theme_id, h.financial_on, h.financial_changed, h.financial_judged, h.news_ratio, h.computed_at
          FROM quarterly_theme_classification_history h
          JOIN (SELECT theme_id, MAX(computed_at) AS at FROM quarterly_theme_classification_history
                WHERE market = ? AND fiscal_year = ? AND fiscal_quarter = ? GROUP BY theme_id) m
            ON m.theme_id = h.theme_id AND m.at = h.computed_at
          WHERE h.market = ? AND h.fiscal_year = ? AND h.fiscal_quarter = ?
        `,
        args: [market, fiscalYear, fiscalQuarter, market, fiscalYear, fiscalQuarter],
      });
      h.rows.forEach((r) => {
        latestFin[r[0] as string] = { on: toBool(r[1]), changed: toNum(r[2]), judged: toNum(r[3]), news_ratio: toNum(r[4]), at: String(r[5]) };
      });
    } catch { /* 이력 표가 아직 없음 */ }

    const themes = themesRes.rows.map((r) => ({
      theme_id: r[0] as string,
      classification: r[1] as string | null,
      financial_on: toBool(r[2]),
      financial_changed: toNum(r[3]),
      financial_judged: toNum(r[4]),
      financial_ratio: toNum(r[5]),
      news_high: toBool(r[6]),
      news_ratio: toNum(r[7]),
      news_this_quarter: toNum(r[8]),
      previous_classification: prevByTheme[r[0] as string] ?? null,
      // 화면 행보다 나중에 다시 계산한 값이 있을 때만
      latest_financial: latestFin[r[0] as string] && latestFin[r[0] as string].at > String(r[9] ?? "") ? latestFin[r[0] as string] : null,
    }));

    // 계산한 날(2026-11-08 화면 점검) - '기준 분기 2026Q3'만 보면 언제 값인지 몰랐다(9/23 계산)
    // 분류가 있는 행의 계산 시각(2026-11-17) - 분류 없이 남은 행(그 뒤 새로 생긴 테마 등)의 시각이 머리에 나오면 '11/17 계산'으로 잘못 읽힌다
    const atOf = (rows: typeof themesRes.rows) => rows.map((r) => String(r[9] ?? "")).filter(Boolean).sort().pop() ?? null;
    const computedAt = atOf(themesRes.rows.filter((r) => r[1] != null)) ?? atOf(themesRes.rows);
    const latestAt = Object.values(latestFin).map((x) => x.at).sort().pop() ?? null;
    const rerun = latestAt && computedAt && latestAt > computedAt ? Object.values(latestFin).filter((x) => x.at === latestAt) : [];
    return NextResponse.json({
      fiscal_year: fiscalYear,
      fiscal_quarter: fiscalQuarter,
      computed_at: computedAt,
      // 나중에 다시 계산했는데 뉴스 비율이 전부 비었으면(수집원 변경) 화면이 그 이유를 적는다
      rerun_at: rerun.length ? latestAt : null,
      rerun_news_unavailable: rerun.length > 0 && rerun.every((x) => x.news_ratio == null),
      market_reference: marketReference,
      themes,
    });
  } catch (err) {
    console.error("[api/quarterly] error:", err);
    return NextResponse.json({ fiscal_year: null, fiscal_quarter: null, market_reference: null, themes: [] });
  }
}
