import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";
import profiles from "@/src/data/companyProfiles.json";
import { krStockName } from "@/src/lib/krStockNames";

export const dynamic = "force-dynamic";

// 기업 기초조사 카드(2026-11-05, 사용자 결정 - 마스터 플랜 2단계 첫 항목). 리서치 실행 가이드 2단계 순서에 맞춘 한 종목 묶음.
// 워치리스트 후보가 아닌 종목(테마 소속·13F·공시에 나온 종목)도 열린다. 숫자는 전부 저장된 값 그대로(원칙 2),
// 종합 점수·매수 판단 없음(원칙 1), 값이 없으면 null - 화면이 "데이터 부족"으로 보인다(원칙 4).
// 내러티브·내부자·8-K·13F·피어·체크리스트는 화면이 기존 API(StockSections)를 따로 부른다 - 여기선 그 밖의 것만.

type Profile = { n?: string; s?: string; i?: string; d?: string };
const PROFILES = profiles as unknown as Record<"US" | "KR", Record<string, Profile>>;

const MARGIN_STEP = 0.01;   // src/analyzers/company_growth.py와 같은 경계(±1%p)
const FS_PREF = ["CFS", "OFS", "NA"];
const SRC_PREF = new Set(["DART", "SEC"]);

type QRow = { fy: number; fq: number; revenue: number | null; operating_income: number | null; net_income: number | null;
              source: string; fs_div: string; collected_at: string; derived?: string };

// src/db/quarterly_financials.py _rank와 같은 순서: 연결 우선 → 공시 원본(DART·SEC) → 늦게 수집한 것
function rank(r: QRow): [number, number, string] {
  const i = FS_PREF.indexOf(r.fs_div || "NA");
  return [i < 0 ? 0 : FS_PREF.length - i, SRC_PREF.has(r.source) ? 1 : 0, r.collected_at || ""];
}
function better(a: QRow, b: QRow): boolean {
  const ra = rank(a), rb = rank(b);
  for (let k = 0; k < 3; k++) if (ra[k] !== rb[k]) return ra[k] > rb[k];
  return false;
}

async function safe<T>(f: () => Promise<T>, fallback: T): Promise<T> {
  try { return await f(); } catch { return fallback; }
}

export async function GET(request: Request) {
  const raw = (new URL(request.url).searchParams.get("stock") ?? "").trim();
  const [m, ...rest] = raw.split(":");
  const market = m === "KR" ? "KR" : m === "US" ? "US" : null;
  const symbol = rest.join(":").trim().toUpperCase();
  if (!market || !symbol) return NextResponse.json({ error: "stock=US:MU 형식" }, { status: 400 });

  const client = getClient();
  const rows = async (sql: string, args: (string | number)[] = []) => (await client.execute({ sql, args })).rows;

  const prof = PROFILES[market]?.[symbol] ?? null;

  // 소속 테마 - 테마마다 가장 최근 승인 run(ticker-themes API와 같은 기준) + 그 테마의 최신 세 축·라벨 + 이 종목의 근거
  const themes = await safe(async () => (await rows(`
      WITH latest_runs AS (SELECT theme_id, MAX(run_id) AS run_id FROM theme_members WHERE market = ? AND approved = 1 GROUP BY theme_id)
      SELECT tm.theme_id, tm.linkage, tm.stage, tm.evidence, ts.label, ts.news_arrow, ts.earn_arrow, ts.price_arrow, ts.week_start, tm.run_id
      FROM theme_members tm
      JOIN latest_runs lr ON lr.theme_id = tm.theme_id AND lr.run_id = tm.run_id
      LEFT JOIN theme_signals ts ON ts.theme_id = tm.theme_id AND ts.market = ?
        AND ts.week_start = (SELECT MAX(week_start) FROM theme_signals WHERE market = ?)
      WHERE tm.ticker = ? AND tm.market = ? AND tm.approved = 1
      ORDER BY CASE tm.linkage WHEN 'direct' THEN 0 WHEN 'partial' THEN 1 ELSE 2 END, tm.theme_id`,
    [market, market, market, symbol, market])).map((r) => ({
      theme_id: r[0] as string, linkage: (r[1] as string) ?? "direct", stage: r[2] as string | null, evidence: r[3] as string | null,
      label: r[4] as string | null, news: r[5] as string | null, earn: r[6] as string | null, price: r[7] as string | null,
      week: r[8] as string | null, run_id: r[9] as string, segment: null as number | null, segment_label: null as string | null,
    })), []);
  // 가치사슬 구간(2026-11-05) - 테마마다 최신 승인 run에서 가장 늦게 분류한 값
  await safe(async () => {
    const segRows = await rows(`SELECT theme_id, run_id, segment, segment_label FROM theme_member_segments
                                WHERE market = ? AND ticker = ? ORDER BY classified_at`, [market, symbol]);
    for (const t of themes) {
      for (const r of segRows) if (r[0] === t.theme_id && r[1] === t.run_id) { t.segment = Number(r[2]); t.segment_label = (r[3] as string | null) ?? null; }
    }
  }, undefined);

  // 재무 필터 판정(스크리닝 대상이면) + 워치리스트 후보 칸(후보일 때만)
  const screening = await safe(async () => {
    const r = (await rows("SELECT status, red_flags, piotroski, roe, screened_at FROM watchlist_screening_results WHERE market = ? AND symbol = ?", [market, symbol]))[0];
    if (!r) return null;
    let reasons: string[] = [];
    try { reasons = JSON.parse(String(r[1] ?? "[]")); } catch { reasons = r[1] ? [String(r[1])] : []; }
    return { status: r[0] as string, reasons, piotroski: r[2] == null ? null : Number(r[2]), roe: r[3] == null ? null : Number(r[3]), screened_at: r[4] as string };
  }, null);
  const candidate = await safe(async () => {
    const res = await client.execute({ sql: "SELECT * FROM watchlist_candidates WHERE market = ? AND symbol = ?", args: [market, symbol] });
    const r = res.rows[0];
    if (!r) return null;
    const o: Record<string, unknown> = {};
    res.columns.forEach((c, i) => { o[c] = r[i]; });
    const pick = ["name", "market_cap", "piotroski", "debt_ratio", "interest_coverage", "roe", "psr", "per", "valuation_tier",
      "revenue_cagr_3y", "revenue_yoy", "growth_tier", "op_margin_direction", "op_margin_q_status", "rev_ttm_yoy", "fcf_yield_3y", "screened_at",
      "valuation_basis", "psr_peer_median", "psr_peer_n"];   // 업종 기준 밸류 등급(2026-11-13)
    return Object.fromEntries(pick.filter((k) => k in o).map((k) => [k, o[k]]));
  }, null);

  // 분기 재무 - 공시 원본 표에서 분기마다 하나(파이썬 select_quarters와 같은 규칙), 최근 8분기
  // 거둬들인 분기(같은 출처·구분의 마지막 행이 derived='withdrawn')와 아직 끝나지 않은 분기는 뺀다 - 파이썬 _best_per_quarter와 같은 규칙(2026-11-05)
  const quarters = await safe(async () => {
    const all: QRow[] = (await rows(`SELECT fiscal_year, fiscal_quarter, revenue, operating_income, net_income, source, fs_div, collected_at, derived
                                FROM quarterly_financials_raw WHERE market = ? AND ticker = ?`, [market, symbol])).map((r) => ({
      fy: Number(r[0]), fq: Number(r[1]), revenue: r[2] == null ? null : Number(r[2]),
      operating_income: r[3] == null ? null : Number(r[3]), net_income: r[4] == null ? null : Number(r[4]),
      source: String(r[5] ?? ""), fs_div: String(r[6] ?? "NA"), collected_at: String(r[7] ?? ""), derived: String(r[8] ?? "") }));
    const latest = new Map<string, QRow>();
    for (const q of all) {
      const k = `${q.fy}-${q.fq}-${q.source}-${q.fs_div}`;
      const cur = latest.get(k);
      if (!cur || q.collected_at > cur.collected_at) latest.set(k, q);
    }
    const today = new Date().toISOString().slice(0, 10);
    const qEnd = (y: number, q: number) => new Date(Date.UTC(y, q * 3, 0)).toISOString().slice(0, 10);
    const best = new Map<string, QRow>();
    for (const q of all) {
      const l = latest.get(`${q.fy}-${q.fq}-${q.source}-${q.fs_div}`)!;
      if (l.derived === "withdrawn" || qEnd(q.fy, q.fq) > today) continue;
      const k = `${q.fy}-${q.fq}`;
      const cur = best.get(k);
      if (!cur || better(q, cur)) best.set(k, q);
    }
    return [...best.values()].sort((a, b) => b.fy - a.fy || b.fq - a.fq).slice(0, 8)
      .map((q) => ({ quarter: `${q.fy}-Q${q.fq}`, revenue: q.revenue, operating_income: q.operating_income, net_income: q.net_income,
                     source: q.source }));
  }, [] as { quarter: string; revenue: number | null; operating_income: number | null; net_income: number | null; source: string }[]);

  // 사업 요약 한국어판(2026-11-05, company_summaries_ko - GPT가 원문을 옮긴 것, 숫자 문장은 뺌). 가장 늦게 만든 행
  const summaryKo = await safe(async () => {
    const r = (await rows("SELECT summary_ko FROM company_summaries_ko WHERE market = ? AND symbol = ? ORDER BY created_at DESC LIMIT 1",
                          [market, symbol]))[0];
    return r ? (r[0] as string) : null;
  }, null as string | null);

  // 최근 일 - 한국 공시(120일), 다음 실적 발표일, 관심도(내러티브), 내 메모, 관찰 노트
  const krDisclosures = market !== "KR" ? [] : await safe(async () => (await rows(
    `SELECT rcept_no, rcept_dt, kind, report_nm, payload FROM kr_disclosures WHERE stock_code = ? AND rcept_dt >= date('now', '-120 days')
     ORDER BY rcept_dt DESC LIMIT 12`, [symbol])).map((r) => {
      let p: Record<string, unknown> = {};
      try { p = JSON.parse(String(r[4] ?? "{}")); } catch { /* 못 읽으면 제목만 */ }
      return { rcept_no: r[0] as string, date: r[1] as string, kind: r[2] as string, title: r[3] as string | null,
               pct: typeof p.pct_of_revenue === "number" ? p.pct_of_revenue : null };
    }), []);
  const nextEarnings = await safe(async () => {
    const r = (await rows(`SELECT earnings_date, earnings_date_end, is_estimate FROM earnings_calendar WHERE market = ? AND ticker = ?
                           AND fetched_on = (SELECT MAX(fetched_on) FROM earnings_calendar WHERE market = ? AND ticker = ?)
                           AND earnings_date_end >= date('now', '-1 day') ORDER BY earnings_date LIMIT 1`, [market, symbol, market, symbol]))[0];
    return r ? { date: r[0] as string, date_end: r[1] as string, estimate: Number(r[2]) === 1 } : null;
  }, null);
  const sentiment = await safe(async () => {
    const r = (await rows("SELECT payload FROM narrative_briefs WHERE market = ? AND symbol = ?", [market, symbol]))[0];
    if (!r) return null;
    const p = JSON.parse(String(r[0]));
    return { now: (p.sentiment ?? null) as string | null, prev: (p.prev_sentiment ?? null) as string | null };
  }, null);
  const mine = await safe(async () => {
    const r = (await rows("SELECT note, added_at FROM my_watchlist WHERE market = ? AND symbol = ?", [market, symbol]))[0];
    return r ? { note: r[0] as string | null, added_at: r[1] as string } : null;
  }, null);
  const notes = await safe(async () => (await rows(
    "SELECT id, created_at, hypothesis FROM observations WHERE kind = 'stock' AND market = ? AND ticker = ? ORDER BY created_at DESC LIMIT 5",
    [market, symbol])).map((r) => ({ id: Number(r[0]), created_at: r[1] as string, hypothesis: r[2] as string })), []);
  const warn8k = market !== "US" ? [] : await safe(async () => (await rows(
    "SELECT filed_on, detail FROM us_8k_filings WHERE symbol = ? AND warn = 1 AND filed_on >= date('now', '-120 days') ORDER BY filed_on DESC LIMIT 5",
    [symbol])).map((r) => {
      let labels: string[] = [];
      try { labels = (JSON.parse(String(r[1])).items ?? []).filter((i: { warn?: boolean }) => i.warn).map((i: { label: string }) => i.label); } catch { /* */ }
      return { date: r[0] as string, labels };
    }), []);

  // ── 주의할 사실(반대 논리의 재료) - 데이터에서 코드가 뽑는다. GPT가 짓지 않는다(원칙 2). 판정이 아니라 "확인해 볼 것" 목록.
  const cautions: { text: string; why: string }[] = [];
  if (screening?.status === "fail")
    cautions.push({ text: "재무 필터 탈락", why: screening.reasons.slice(0, 3).join(" · ") || "탈락 사유 미기록" });
  const q0 = quarters[0], q4 = quarters.find((q) => q.quarter === (q0 ? `${Number(q0.quarter.slice(0, 4)) - 1}${q0.quarter.slice(4)}` : ""));
  if (q0 && q4 && q0.revenue != null && q4.revenue != null && q4.revenue > 0 && q0.revenue < q4.revenue)
    cautions.push({ text: "매출이 1년 전 같은 분기보다 줄었다", why: `${q0.quarter} vs ${q4.quarter}` });
  const margin = (q?: { revenue: number | null; operating_income: number | null }) =>
    q && q.revenue && q.revenue > 0 && q.operating_income != null ? q.operating_income / q.revenue : null;
  const m0 = margin(q0), m4 = margin(q4);
  if (m0 != null && m4 != null && m0 - m4 <= -MARGIN_STEP)
    cautions.push({ text: "영업이익률이 1년 전 같은 분기보다 낮아졌다", why: `${q0!.quarter} vs ${q4!.quarter}` });
  if (q0 && q0.net_income != null && q0.net_income < 0)
    cautions.push({ text: "최근 분기 순손실", why: q0.quarter });
  if (candidate && String(candidate.valuation_tier ?? "").includes("비싼"))
    cautions.push({ text: String(candidate.valuation_basis ?? "").startsWith("업종") || String(candidate.valuation_basis ?? "").startsWith("섹터")
      ? `밸류 HIGH - 같은 ${String(candidate.valuation_basis).split(" · ")[0]} 동료 4곳 중 3곳보다 PSR이 높음` : "밸류 HIGH - 같은 시장 후보 중 비싼 쪽",
      why: candidate.psr_peer_median != null ? `PSR ${Number(candidate.psr).toFixed(2)} · 중앙값 ${Number(candidate.psr_peer_median).toFixed(2)}` : "워치리스트 밸류 등급" });
  for (const f of warn8k) cautions.push({ text: `미국 8-K 주의 공시: ${f.labels.join(", ") || "주의 항목"}`, why: f.date });
  for (const d of krDisclosures.filter((x) => x.kind === "termination"))
    cautions.push({ text: "공급계약 해지 공시", why: d.date + (d.pct != null ? ` · 매출 대비 ${d.pct.toFixed(1)}%` : "") });
  for (const t of themes.filter((x) => x.label === "Overheated Buzz"))
    cautions.push({ text: `소속 테마에 '기대 과열' 라벨 - 뉴스·주가가 실적보다 앞섬`, why: t.theme_id });
  if (sentiment?.now === "HOT" && q0 && q4 && q0.revenue != null && q4.revenue != null && q0.revenue < q4.revenue)
    cautions.push({ text: "관심도는 높은데 매출은 줄었다", why: "관심도 HOT · 매출 감소" });
  if (themes.length > 0 && themes.every((t) => t.linkage === "peripheral"))
    cautions.push({ text: "소속 테마가 모두 간접(peripheral) - 테마가 좋아도 실적과의 연결이 약할 수 있다", why: "테마 매핑" });

  return NextResponse.json({
    market, symbol,
    name: (candidate?.name as string | undefined) ?? prof?.n ?? (market === "KR" ? krStockName(symbol) : null) ?? null,
    profile: prof ? { sector: prof.s ?? null, industry: prof.i ?? null, summary: prof.d ?? null, summary_ko: summaryKo } : null,
    themes: themes.map(({ run_id: _r, ...t }) => t), screening, candidate, quarters, kr_disclosures: krDisclosures, next_earnings: nextEarnings,
    sentiment, mine, notes, cautions,
  });
}
