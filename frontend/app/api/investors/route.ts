import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 유명 투자자 13F(2026-10-25, scripts/collect_13f.py) - 운용사마다 가장 최근 분기의 보유·직전 분기 비교.
// 숫자는 신고서 값 그대로(평가액은 분기 말 기준), 순위·점수 없음. 주식만(풋·콜 옵션 줄은 뺀다).
// ?symbol=TICKER면 그 종목을 들고 있는(또는 이번 분기 다 판) 운용사 목록 - 종목 상세용.
type Row = { manager_id: string; period: string; ticker: string | null; issuer: string | null; cusip: string; shares: number;
  value: number; weight: number | null; status: string | null; prev_shares: number | null; prev_value: number | null;
  share_chg: number | null; filed_on: string | null };
const num = (v: unknown) => (v == null || v === "" ? null : Number(v));
// 확신 매수 기준(2026-10-26 사용자 결정) - 새로 산 종목이 그 운용사 주식 보유의 3% 이상. 임의 기준이라 데이터를 보고 조정.
const CONVICTION_MIN = 0.03;

async function latestRows(): Promise<Row[]> {
  const client = getClient();
  const rs = await client.execute(`
    SELECT p.manager_id, p.period, p.ticker, p.issuer, p.cusip, p.shares, p.value, p.weight, p.status, p.prev_shares, p.prev_value,
           p.share_chg, p.filed_on
    FROM inst_13f_positions p
    JOIN (SELECT manager_id, MAX(period) AS period FROM inst_13f_positions GROUP BY manager_id) l
      ON l.manager_id = p.manager_id AND l.period = p.period
    WHERE p.put_call = ''`);
  return rs.rows.map((r) => ({
    manager_id: String(r.manager_id), period: String(r.period), ticker: r.ticker == null ? null : String(r.ticker),
    issuer: r.issuer == null ? null : String(r.issuer), cusip: String(r.cusip), shares: num(r.shares) ?? 0, value: num(r.value) ?? 0,
    weight: num(r.weight), status: r.status == null ? null : String(r.status), prev_shares: num(r.prev_shares),
    prev_value: num(r.prev_value), share_chg: num(r.share_chg), filed_on: r.filed_on == null ? null : String(r.filed_on),
  }));
}

// 트랩 필터 판정(미국 유니버스만 있음) + 워치리스트 후보 여부 - 없으면 '미확인'(원칙 4)
async function screening(tickers: string[]): Promise<Record<string, { status: string; piotroski: number | null; candidate: boolean }>> {
  const out: Record<string, { status: string; piotroski: number | null; candidate: boolean }> = {};
  if (tickers.length === 0) return out;
  const client = getClient();
  for (let i = 0; i < tickers.length; i += 200) {
    const chunk = tickers.slice(i, i + 200);
    const ph = chunk.map(() => "?").join(",");
    try {
      const rs = await client.execute({ sql: `SELECT symbol, status, piotroski FROM watchlist_screening_results WHERE market = 'US' AND symbol IN (${ph})`, args: chunk });
      for (const r of rs.rows) out[String(r.symbol)] = { status: String(r.status), piotroski: num(r.piotroski), candidate: false };
      const cs = await client.execute({ sql: `SELECT symbol FROM watchlist_candidates WHERE market = 'US' AND symbol IN (${ph})`, args: chunk });
      for (const r of cs.rows) (out[String(r.symbol)] ??= { status: "pass", piotroski: null, candidate: true }).candidate = true;
    } catch { /* 표 없음 - 미확인으로 */ }
  }
  return out;
}

const pick = (r: Row) => ({ ticker: r.ticker, issuer: r.issuer, value: r.value, weight: r.weight, status: r.status,
  share_chg: r.share_chg, prev_value: r.prev_value });

export async function GET(request: Request) {
  const symbol = new URL(request.url).searchParams.get("symbol")?.toUpperCase() ?? null;
  try {
    const rows = await latestRows();
    if (symbol) {
      const mine = rows.filter((r) => r.ticker === symbol && (r.shares > 0 || r.status === "sold"));
      return NextResponse.json({ holders: mine.map((r) => ({ manager_id: r.manager_id, period: r.period, filed_on: r.filed_on, ...pick(r), shares: r.shares })) });
    }
    const byManager: Record<string, Row[]> = {};
    for (const r of rows) (byManager[r.manager_id] ??= []).push(r);
    const managers = Object.entries(byManager).map(([id, rs]) => {
      const held = rs.filter((r) => r.shares > 0);
      const count = (s: string) => rs.filter((r) => r.status === s).length;
      const top = (s: string, key: (r: Row) => number, n: number) => rs.filter((r) => r.status === s).sort((a, b) => key(b) - key(a)).slice(0, n).map(pick);
      return {
        id, period: rs[0].period, filed_on: rs.reduce((m, r) => (r.filed_on && r.filed_on > m ? r.filed_on : m), ""),
        positions: held.length, value_total: held.reduce((n, r) => n + r.value, 0),
        compared: rs.some((r) => r.status != null),
        counts: { new: count("new"), added: count("added"), reduced: count("reduced"), sold: count("sold") },
        top_holdings: held.sort((a, b) => b.value - a.value).slice(0, 8).map(pick),   // 비중 막대용 상위 8(나머지는 화면에서 '기타')
        new: top("new", (r) => r.value, 12),
        added: top("added", (r) => r.value - (r.prev_value ?? 0), 8),
        reduced: top("reduced", (r) => (r.prev_value ?? 0) - r.value, 8),
        sold: top("sold", (r) => r.prev_value ?? 0, 12),
      };
    });
    // 여러 곳이 함께 새로 사거나 늘린 종목(각 운용사의 가장 최근 분기 기준)
    const together: Record<string, { ticker: string; issuer: string | null; buyers: { manager_id: string; status: string; value: number; weight: number | null }[] }> = {};
    for (const r of rows) {
      if (!r.ticker || (r.status !== "new" && r.status !== "added")) continue;
      (together[r.ticker] ??= { ticker: r.ticker, issuer: r.issuer, buyers: [] }).buyers.push({ manager_id: r.manager_id, status: r.status, value: r.value, weight: r.weight });
    }
    // 정렬: 겹친 운용사 수 → 그중 새로 산 곳 수 → 합계 평가액(같은 곳 수면 회전이 잦은 곳끼리의 우연한 '늘림'보다 '새로'를 앞에). 점수 아님
    const newN = (t: { buyers: { status: string }[] }) => t.buyers.filter((x) => x.status === "new").length;
    const valSum = (t: { buyers: { value: number }[] }) => t.buyers.reduce((n, x) => n + x.value, 0);
    const shared = Object.values(together).filter((t) => t.buyers.length >= 2)
      .sort((a, b) => b.buyers.length - a.buyers.length || newN(b) - newN(a) || valSum(b) - valSum(a));
    // 확신 매수 - 새로 샀는데 비중이 큰 종목(운용사가 새 종목에 크게 실은 경우). 비중 큰 순
    const conviction = rows.filter((r) => r.status === "new" && (r.weight ?? 0) >= CONVICTION_MIN)
      .sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0))
      .map((r) => ({ manager_id: r.manager_id, period: r.period, ...pick(r) }));
    const tickers = Array.from(new Set([...managers.flatMap((m) => [...m.new, ...m.added].map((x) => x.ticker)), ...shared.map((t) => t.ticker),
      ...conviction.map((x) => x.ticker)]
      .filter((t): t is string => !!t)));
    const unmapped = rows.filter((r) => !r.ticker && r.shares > 0).length;
    return NextResponse.json({ managers, shared, conviction, conviction_min: CONVICTION_MIN, screening: await screening(tickers), unmapped });
  } catch {
    return NextResponse.json({ managers: [], shared: [], conviction: [], conviction_min: CONVICTION_MIN, screening: {}, unmapped: 0 });
  }
}
