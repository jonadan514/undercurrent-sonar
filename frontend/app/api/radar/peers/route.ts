import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";
import profiles from "@/src/data/companyProfiles.json";

export const dynamic = "force-dynamic";

// 테마 동료 비교(2026-10-25) - 종목 상세에서 "이 종목이 자기 테마 안에서 어디쯤인가".
// 이 종목이 사업 소속(직접·부분)인 테마마다, 그 테마 소속 기업들의 최근 주 값으로 중앙값·가운데 절반(25~75%)을 낸다.
// 숫자는 저장된 값 그대로(theme_member_signals: 매출 YoY·영업이익률·FCF 수익률, watchlist_screening_results: ROE).
// 순위·점수는 만들지 않는다(원칙 1). 값이 있는 동료가 PEER_MIN곳 미만이면 중앙값을 내지 않는다(데이터 부족, 원칙 4).
// 2026-11-11: 동료 이름과 값(peers)도 같이 - 중앙값만으로는 누구와 견주는지 몰랐다. 줄 순서는 이름순(값 순 정렬 = 순위라 안 함).
// 업종 동료(industry): 테마 소속이 없는 종목도 같은 시장·같은 업종(회사 정보의 yfinance industry) 유니버스 종목과 견준다.
// 값은 compute_theme_earnings.py가 유니버스 전체에 쓰는 universe_peer_metrics(테마 동료와 같은 함수·단위)의 최근 주.
const PEER_MIN = 5;
type Profile = { n?: string; s?: string; i?: string; g?: [string, string][] };
const PROFILES = profiles as unknown as Record<"US" | "KR", Record<string, Profile>>;
const METRICS = ["rev_yoy", "om_now", "fcf_yield_3y", "roe", "psr"] as const;   // psr은 업종 묶음에만(2026-11-13)
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
    if (themeIds.length === 0) return NextResponse.json({ peer_min: PEER_MIN, themes: [], industry: await industryPeers(client, market, symbol) });

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
      const vals = members.map((r) => ({
        symbol: String(r.ticker),
        rev_yoy: num(r.rev_yoy), om_now: num(r.om_now), fcf_yield_3y: num((r as Record<string, unknown>).fcf_yield_3y),
        roe: roe[String(r.ticker)] ?? null, psr: null,
      }));
      return { theme_id: tid, week: members[0] ? String(members[0].week_start) : null, ...summarize(vals, symbol, market) };
    }).filter((t) => t.members > 0);

    return NextResponse.json({ peer_min: PEER_MIN, themes, industry: await industryPeers(client, market, symbol) });
  } catch (err) {
    console.error("[api/radar/peers] error:", err);
    return NextResponse.json({ themes: [], industry: null });
  }
}

type PeerVals = { symbol: string } & Record<Metric, number | null>;

// 한 묶음(테마 또는 업종)의 지표별 중앙값·가운데 절반과 동료 줄(이름순)
function summarize(vals: PeerVals[], symbol: string, market: "US" | "KR") {
  const self = vals.find((v) => v.symbol === symbol);
  // 값이 하나도 없는 지표(테마 묶음의 PSR)는 빼서 화면 줄·열이 생기지 않게
  const metrics = Object.fromEntries(METRICS.filter((m) => vals.some((v) => v[m] != null)).map((m) => {
    const xs = vals.map((v) => v[m]).filter((v): v is number => v != null).sort((a, b) => a - b);
    const enough = xs.length >= PEER_MIN;
    return [m, {
      self: self ? self[m] : null,
      n: xs.length,
      median: enough ? quantile(xs, 0.5) : null,
      q1: enough ? quantile(xs, 0.25) : null,
      q3: enough ? quantile(xs, 0.75) : null,
    }];
  }));
  const nameOf = (sym: string) => PROFILES[market]?.[sym]?.n ?? null;
  const peers = vals.map((v) => ({ ...v, name: nameOf(v.symbol) }))
    .sort((a, b) => (a.name ?? a.symbol).localeCompare(b.name ?? b.symbol, "ko"));
  return { members: vals.length, metrics, peers };
}

// 비교 묶음 순서 - compute_watchlist_valuation(company_valuation.peer_levels)과 같게(2026-11-13):
// 미국 yfinance 업종 → 섹터, 한국 yfinance 업종 → KSIC 소분류 → KSIC 중분류(한국은 섹터로 넓히지 않는다).
type Level = { basis: string; key: string; name: string };
function levelsOf(market: "US" | "KR", p: Profile | undefined): Level[] {
  if (!p) return [];
  const out: Level[] = [];
  if (p.i) out.push({ basis: "업종", key: `i:${p.i}`, name: p.i });
  if (market === "KR") (p.g ?? []).forEach(([key, name], i) => out.push({ basis: i === 0 ? "업종" : "업종 대분류", key, name }));
  else if (p.s) out.push({ basis: "섹터", key: `s:${p.s}`, name: p.s });
  return out;
}

async function industryPeers(client: ReturnType<typeof getClient>, market: "US" | "KR", symbol: string) {
  const prof = PROFILES[market]?.[symbol];
  const all = Object.entries(PROFILES[market] ?? {});
  let lv: Level | null = null;
  let syms: string[] = [];
  for (const l of levelsOf(market, prof)) {
    const ms = all.filter(([, p]) => levelsOf(market, p).some((x) => x.key === l.key)).map(([k]) => k);
    if (ms.length >= PEER_MIN) { lv = l; syms = ms; break; }
  }
  if (!lv) return null;
  try {
    const ph = syms.map(() => "?").join(",");
    const rs = await client.execute({
      sql: `SELECT symbol, week_start, rev_yoy, om_now, fcf_yield_3y, psr FROM universe_peer_metrics
            WHERE market = ? AND week_start = (SELECT MAX(week_start) FROM universe_peer_metrics WHERE market = ?) AND symbol IN (${ph})`,
      args: [market, market, ...syms],
    });
    if (rs.rows.length === 0) return null;
    const roe: Record<string, number | null> = {};
    const rr = await client.execute({
      sql: `SELECT symbol, roe FROM watchlist_screening_results WHERE market = ? AND symbol IN (${ph})`,
      args: [market, ...syms],
    });
    for (const r of rr.rows) roe[String(r.symbol)] = num(r.roe);
    const vals: PeerVals[] = rs.rows.map((r) => ({
      symbol: String(r.symbol), rev_yoy: num(r.rev_yoy), om_now: num(r.om_now), fcf_yield_3y: num(r.fcf_yield_3y),
      roe: roe[String(r.symbol)] ?? null, psr: num(r.psr),
    }));
    return { basis: lv.basis, sector: lv.key.startsWith("i:") ? prof?.s ?? null : null, industry: lv.name,
             week: String(rs.rows[0].week_start), ...summarize(vals, symbol, market) };
  } catch {
    return null;   // 표가 아직 없으면(첫 주간 계산 전) 업종 칸만 빠진다
  }
}
