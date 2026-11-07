import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";
import { krStockName } from "@/src/lib/krStockNames";
import { themeName } from "@/src/lib/themeNames";
import PROFILES_RAW from "@/src/data/companyProfiles.json";

export const dynamic = "force-dynamic";

// 일정(2026-11-07, 마스터 플랜 2단계 '일정 기능'). 한 달치 일정을 한 곳에 - 새로 수집하지 않고 이미 쌓인 표만 읽는다.
//  · 실적 발표: earnings_calendar(yfinance, 워치리스트 후보·내 관심·관찰 노트·테마 소속(11/8~) 종목, 매주 일요일 수집) + 한국 결산실적 공시예고(DART,
//    회사가 정한 날짜라 yfinance보다 우선). 지난 날짜는 '그 날짜가 지나기 전에 마지막으로 받은 값'을 쓴다(아래 pickEarnings).
//  · 관찰 노트 회고: 작성 주 + 4주·12주가 지나면 그다음 월요일 주간 브리핑에 회고가 붙는다(scripts/review_observations.py).
//  · 공시 마감(13F·한국 분기보고서)과 도구 일정(주간 브리핑·월간 보고서)은 정해진 날짜라 여기서 만든다.
// 점수·순위 없음(원칙 1) - 표시 순서는 내 관심 → 노트 → 후보 → 테마 → 이름.

const PROFILES = PROFILES_RAW as Record<string, Record<string, { n?: string }>>;

type Tag = "my" | "note" | "candidate" | "theme";
export interface CalEvent {
  date: string;                 // YYYY-MM-DD
  kind: "earnings" | "review" | "deadline" | "tool";
  market?: "US" | "KR";
  symbol?: string;
  name?: string;
  estimate?: boolean;           // 실적 발표일이 회사 확정 전 예상치
  source?: string;              // yfinance | DART
  tags?: Tag[];
  themes?: string[];            // 소속 테마 이름(테마 태그일 때)
  text?: string;                // 마감·도구 일정·회고 설명
  href?: string;
}

// 미국 13F는 분기 끝 + 45일, 한국 분기·반기보고서도 45일, 사업보고서는 90일(3/31). 주말이면 실제 마감은 다음 영업일일 수 있다.
const DEADLINES: [number, number, string][] = [
  [2, 14, "미국 13F 4분기 보유 신고 마감"],
  [3, 31, "한국 사업보고서 마감"],
  [5, 15, "미국 13F 1분기 마감 · 한국 1분기보고서 마감"],
  [8, 14, "미국 13F 2분기 마감 · 한국 반기보고서 마감"],
  [11, 14, "미국 13F 3분기 마감 · 한국 3분기보고서 마감"],
];
const CHECKPOINTS = [4, 12];
const FIRST_MONTHLY = "2026-11-01";   // 월간 보고서는 10월분(11월 첫 월요일)부터 - 그 전 달 링크는 빈 화면이라 표시 안 함

const iso = (d: Date) => d.toISOString().slice(0, 10);
const addDays = (s: string, n: number) => { const d = new Date(`${s}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return iso(d); };

function monthRange(month: string): [string, string] {
  const [y, m] = month.split("-").map(Number);
  const start = new Date(Date.UTC(y, m - 1, 1));
  const end = new Date(Date.UTC(y, m, 0));
  return [iso(start), iso(end)];
}

interface EarnRow { ticker: string; market: string; earnings_date: string; is_estimate: unknown; fetched_on: string }

/** 종목마다 이 달에 보일 실적 발표일 하나.
 *  달 안에 든 행 중 가장 늦게 받은 것을 쓰되, 그 뒤에 받은 행이 다른 날짜를 말하고 그때 아직 이 날짜가 오지 않았으면 날짜가 바뀐 것이라 뺀다
 *  (예상 11/5 → 확정 11/12로 바뀐 경우 11/5에 남지 않게). 날짜가 지난 뒤 받은 행이 다음 분기 날짜인 건 정상(발표가 끝남)이라 남긴다. */
function pickEarnings(inMonth: EarnRow[], latest: Map<string, EarnRow>): EarnRow[] {
  const best = new Map<string, EarnRow>();
  for (const r of inMonth) {
    const k = `${r.market}:${r.ticker}`;
    const cur = best.get(k);
    if (!cur || r.fetched_on > cur.fetched_on) best.set(k, r);
  }
  const out: EarnRow[] = [];
  for (const [k, r] of best) {
    const last = latest.get(k);
    if (last && last.fetched_on > r.fetched_on && last.earnings_date !== r.earnings_date && last.fetched_on < r.earnings_date) continue;
    out.push(r);
  }
  return out;
}

const truthy = (v: unknown) => v === 1 || v === "1" || v === true;

export async function GET(req: Request) {
  const want = new URL(req.url).searchParams.get("month");
  const today = iso(new Date());
  const month = want && /^\d{4}-\d{2}$/.test(want) ? want : today.slice(0, 7);
  const [from, to] = monthRange(month);
  const events: CalEvent[] = [];
  const notes: string[] = [];
  try {
    const client = getClient();
    const q = async (sql: string, args: (string | number)[] = []) => {
      try { return (await client.execute({ sql, args })).rows as unknown as Record<string, unknown>[]; }
      catch (e) { console.error("[api/calendar]", (e as Error).message); return []; }
    };

    // ── 태그(내 관심·노트·후보·테마) ──
    const tags = new Map<string, Set<Tag>>();
    const names = new Map<string, string>();
    const themesOf = new Map<string, Set<string>>();
    const tag = (k: string, t: Tag) => { if (!tags.has(k)) tags.set(k, new Set()); tags.get(k)!.add(t); };
    for (const r of await q("SELECT market, symbol, name FROM my_watchlist")) {
      const k = `${r.market}:${r.symbol}`; tag(k, "my"); if (r.name) names.set(k, String(r.name));
    }
    for (const r of await q("SELECT DISTINCT market, ticker FROM observations WHERE kind = 'stock' AND ticker IS NOT NULL")) tag(`${r.market}:${r.ticker}`, "note");
    for (const r of await q("SELECT market, symbol, name FROM watchlist_candidates")) {
      const k = `${r.market}:${r.symbol}`; tag(k, "candidate"); if (r.name && !names.has(k)) names.set(k, String(r.name));
    }
    for (const r of await q(`WITH lr AS (SELECT theme_id, market, MAX(run_id) AS run_id FROM theme_members WHERE approved = 1 GROUP BY theme_id, market)
                             SELECT tm.market, tm.ticker, tm.theme_id FROM theme_members tm JOIN lr ON lr.theme_id = tm.theme_id AND lr.market = tm.market
                             AND lr.run_id = tm.run_id WHERE tm.approved = 1 AND tm.linkage IN ('direct','partial')`)) {
      const k = `${r.market}:${r.ticker}`; tag(k, "theme");
      if (!themesOf.has(k)) themesOf.set(k, new Set());
      themesOf.get(k)!.add(themeName(String(r.theme_id)).ko);
    }
    const nameOf = (market: string, symbol: string) => {
      const k = `${market}:${symbol}`;
      const n = PROFILES[market]?.[symbol]?.n || names.get(k);
      if (n && n !== symbol) return n.replace(/,?\s+(Inc\.?|Corp\.?|Corporation|Co\.?|Ltd\.?|plc|PLC)$/i, "");
      return market === "KR" ? krStockName(symbol) : symbol;
    };

    // ── 실적 발표 ──
    const inMonth = (await q(`SELECT ticker, market, earnings_date, is_estimate, fetched_on FROM earnings_calendar
                               WHERE earnings_date >= ? AND earnings_date <= ?`, [from, to])) as unknown as EarnRow[];
    const latestRows = (await q(`SELECT e.ticker, e.market, e.earnings_date, e.is_estimate, e.fetched_on FROM earnings_calendar e
                                  JOIN (SELECT ticker, market, MAX(fetched_on) AS f FROM earnings_calendar GROUP BY ticker, market) l
                                  ON e.ticker = l.ticker AND e.market = l.market AND e.fetched_on = l.f`)) as unknown as EarnRow[];
    const latest = new Map(latestRows.map((r) => [`${r.market}:${r.ticker}`, r]));
    const earn = new Map<string, CalEvent>();
    for (const r of pickEarnings(inMonth, latest)) {
      const k = `${r.market}:${r.ticker}`;
      earn.set(k, { date: String(r.earnings_date).slice(0, 10), kind: "earnings", market: r.market as "US" | "KR", symbol: r.ticker,
                    estimate: truthy(r.is_estimate), source: "yfinance" });
    }
    // 한국 결산실적 공시예고(DART) - 회사가 정한 날짜. 같은 종목이면 예고가 이긴다(늦게 낸 예고 우선)
    for (const r of await q(`SELECT stock_code, payload, rcept_dt FROM kr_disclosures WHERE kind = 'notice' ORDER BY rcept_dt, rcept_no`)) {
      let d: string | undefined;
      try { d = JSON.parse(String(r.payload)).announce_date; } catch { d = undefined; }
      if (!d || d < from || d > to) continue;
      const k = `KR:${r.stock_code}`;
      if (!tags.has(k)) continue;   // 관심·후보·노트·테마 밖 종목의 예고는 너무 많아 뺀다
      earn.set(k, { date: d, kind: "earnings", market: "KR", symbol: String(r.stock_code), estimate: false, source: "DART" });
    }
    for (const [k, e] of earn) {
      const t = tags.get(k);
      if (!t || !t.size) continue;
      events.push({ ...e, name: nameOf(e.market!, e.symbol!), tags: (["my", "note", "candidate", "theme"] as Tag[]).filter((x) => t.has(x)),
                    themes: [...(themesOf.get(k) ?? [])].slice(0, 3), href: `/company?stock=${encodeURIComponent(k)}` });
    }
    if (!latestRows.length) notes.push("실적 발표일 표(earnings_calendar)가 비어 있습니다.");
    const firstFetch = (await q("SELECT MIN(fetched_on) AS f FROM earnings_calendar"))[0]?.f as string | undefined;
    if (firstFetch && from < firstFetch) {
      notes.push(`실적 발표일은 ${Number(firstFetch.slice(5, 7))}/${Number(firstFetch.slice(8))}부터 받기 시작해 그 전 발표는 없을 수 있습니다.`);
    }

    // ── 관찰 노트 회고 도착(작성 주 + N주가 지난 다음 월요일 브리핑) ──
    for (const r of await q(`SELECT o.id, o.kind, o.market, o.theme_id, o.ticker, o.week_start,
                                    (SELECT GROUP_CONCAT(checkpoint) FROM observation_reviews rv WHERE rv.observation_id = o.id) AS done
                             FROM observations o`)) {
      const done = new Set(String(r.done ?? "").split(",").filter(Boolean).map(Number));
      for (const n of CHECKPOINTS) {
        const d = addDays(String(r.week_start), n * 7 + 7);
        if (d < from || d > to) continue;
        const target = r.kind === "theme" ? `${themeName(String(r.theme_id)).ko} 테마` : nameOf(String(r.market), String(r.ticker));
        events.push({ date: d, kind: "review", market: r.market as "US" | "KR", symbol: r.kind === "stock" ? String(r.ticker) : undefined,
                      name: target, text: `관찰 노트 ${n}주 회고${done.has(n) ? " (도착함)" : ""}`, href: "/notes" });
      }
    }
  } catch (err) {
    console.error("[api/calendar] error:", err);
    notes.push("일정 일부를 불러오지 못했습니다.");
  }

  // ── 정해진 일정: 공시 마감 · 도구 일정 ──
  const [y, m] = month.split("-").map(Number);
  for (const [dm, dd, what] of DEADLINES) if (dm === m) events.push({ date: `${month}-${String(dd).padStart(2, "0")}`, kind: "deadline", text: what });
  for (let d = from; d <= to; d = addDays(d, 1)) {
    const wd = new Date(`${d}T00:00:00Z`).getUTCDay();
    if (wd !== 1) continue;
    events.push({ date: d, kind: "tool", text: "주간 브리핑", href: "/briefing" });
    if (Number(d.slice(8)) <= 7 && d >= FIRST_MONTHLY) {
      const pm = m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, "0")}`;
      events.push({ date: d, kind: "tool", text: `월간 보고서(${Number(pm.slice(5))}월)`, href: `/report?month=${pm}` });
    }
  }

  const rank = (e: CalEvent) => e.kind === "deadline" ? 0 : e.kind === "review" ? 1 : e.kind === "tool" ? 9
    : e.tags?.includes("my") ? 2 : e.tags?.includes("note") ? 3 : e.tags?.includes("candidate") ? 4 : 5;
  events.sort((a, b) => a.date.localeCompare(b.date) || rank(a) - rank(b) || (a.name ?? "").localeCompare(b.name ?? ""));
  return NextResponse.json({ month, from, to, today, events, notes });
}
