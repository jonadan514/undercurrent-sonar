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
    }));

    // 계산한 날(2026-11-08 화면 점검) - '기준 분기 2026Q3'만 보면 언제 값인지 몰랐다(9/23 계산)
    const computedAt = themesRes.rows.map((r) => String(r[9] ?? "")).filter(Boolean).sort().pop() ?? null;
    return NextResponse.json({
      fiscal_year: fiscalYear,
      fiscal_quarter: fiscalQuarter,
      computed_at: computedAt,
      market_reference: marketReference,
      themes,
    });
  } catch (err) {
    console.error("[api/quarterly] error:", err);
    return NextResponse.json({ fiscal_year: null, fiscal_quarter: null, market_reference: null, themes: [] });
  }
}
