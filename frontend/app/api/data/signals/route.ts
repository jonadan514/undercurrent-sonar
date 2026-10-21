import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 신호 사후 확인(2026-10-21, scripts/log_signals.py·compute_signal_outcomes.py).
// 신호가 나온 뒤 4주·12주 초과수익의 분포만 돌려준다 - 건수·중앙값·사분위. 적중률·점수 없음(원칙 1).
// 기준 두 가지: 같은 유니버스 전체 종목 수익률 중앙값(signal_universe_returns - 중소형주 효과를 걷어낸 것), 지수(SPY·KOSPI).
// 표가 아직 없으면(첫 일요일 배치 전) 빈 값.
const HORIZONS = [28, 84] as const;

type Dist = { n: number; median: number | null; q1: number | null; q3: number | null };

function distribution(values: number[]): Dist {
  const v = [...values].sort((a, b) => a - b);
  const n = v.length;
  if (n === 0) return { n: 0, median: null, q1: null, q3: null };
  const q = (p: number) => {
    const i = (n - 1) * p, lo = Math.floor(i), hi = Math.min(lo + 1, n - 1);
    return v[lo] + (v[hi] - v[lo]) * (i - lo);
  };
  return { n, median: q(0.5), q1: q(0.25), q3: q(0.75) };
}

// market: 그 시장에만 있는 신호. expect: 기대 방향이 하락인 신호(해지·주의 종류)는 초과수익이 마이너스여야 '맞은 쪽' - 화면에 같이 적는다.
const GROUPS: { key: string; label: string; desc: string; kind: string; market?: "US" | "KR"; expect?: "down";
                test?: (d: Record<string, unknown>) => boolean }[] = [
  { key: "insider_new", label: "내부자 장내 매수 · 관심 밖", desc: "브리핑 '🆕 새 이름'", kind: "insider_buy", test: (d) => !d.watched },
  { key: "insider_watched", label: "내부자 장내 매수 · 관심 종목", desc: "워치리스트·내 관심·노트·테마 종목", kind: "insider_buy", test: (d) => !!d.watched },
  { key: "turnaround_new", label: "실적 반전 새로 들어옴", desc: "워치리스트 실적 반전 목록 신규", kind: "turnaround_new" },
  { key: "theme_quiet", label: "테마 공시 평소보다 많음 · 축은 조용", desc: "테마 레이더 '축은 조용' 칸 (소속 기업 중앙값)", kind: "theme_busier", test: (d) => d.quiet_axes === true },
  { key: "theme_all", label: "테마 공시 평소보다 많음 · 전체", desc: "축이 움직인 테마 포함 (소속 기업 중앙값)", kind: "theme_busier" },
  // 브리핑 다른 칸(2026-10-21 추가)
  { key: "kr_contract_big", label: "공급계약 · 매출 대비 10% 이상", desc: "브리핑 한국 공시 칸", kind: "kr_contract_big", market: "KR" },
  { key: "kr_termination", label: "공급계약 해지", desc: "브리핑 한국 공시 칸", kind: "kr_termination", market: "KR", expect: "down" },
  { key: "us_8k_contract", label: "8-K 중요 계약 체결 (1.01)", desc: "브리핑 미국 8-K 칸", kind: "us_8k_contract", market: "US" },
  { key: "us_8k_warn", label: "8-K 주의 종류", desc: "해지·손상·구조조정·감사인 교체 등 (붉은 칸)", kind: "us_8k_warn", market: "US", expect: "down" },
  { key: "sentiment_heating", label: "관심도 상승", desc: "브리핑 관심도 칸 (워치리스트 후보)", kind: "sentiment_heating" },
];

export async function GET(request: Request) {
  const market = new URL(request.url).searchParams.get("market") === "KR" ? "KR" : "US";
  try {
    const rs = await getClient().execute({
      sql: `SELECT l.week, l.kind, l.symbol, l.detail, l.backfilled,
                   o.ret_28d, o.bench_28d, o.ret_84d, o.bench_84d, o.n_priced, u.univ_28d, u.univ_84d
            FROM signal_log l LEFT JOIN signal_outcomes o
              ON o.week = l.week AND o.kind = l.kind AND o.market = l.market AND o.symbol = l.symbol
            LEFT JOIN signal_universe_returns u ON u.market = l.market AND u.week = l.week
            WHERE l.market = ? ORDER BY l.week DESC`,
      args: [market],
    });
    type Row = { week: string; kind: string; symbol: string; detail: Record<string, unknown>; backfilled: boolean;
                 ex: Record<number, number | null>; exU: Record<number, number | null>; ret: Record<number, number | null> };
    const rows: Row[] = rs.rows.map((r) => {
      let detail: Record<string, unknown> = {};
      try { detail = JSON.parse(String(r.detail)); } catch { /* 빈 detail */ }
      const ex: Record<number, number | null> = {}, exU: Record<number, number | null> = {}, ret: Record<number, number | null> = {};
      for (const h of HORIZONS) {
        const a = r[`ret_${h}d`] as number | null, b = r[`bench_${h}d`] as number | null, u = r[`univ_${h}d`] as number | null;
        ret[h] = a;
        ex[h] = a != null && b != null ? a - b : null;
        exU[h] = a != null && u != null ? a - u : null;
      }
      return { week: String(r.week), kind: String(r.kind), symbol: String(r.symbol), detail, backfilled: Boolean(r.backfilled), ex, exU, ret };
    });
    const groups = GROUPS.filter((g) => !g.market || g.market === market).map((g) => {
      const mine = rows.filter((r) => r.kind === g.kind && (!g.test || g.test(r.detail)));
      const byH: Record<string, Dist> = {}, byU: Record<string, Dist> = {};
      for (const h of HORIZONS) {
        byH[h] = distribution(mine.map((r) => r.ex[h]).filter((x): x is number => x != null));
        byU[h] = distribution(mine.map((r) => r.exU[h]).filter((x): x is number => x != null));
      }
      return { key: g.key, label: g.label, desc: g.desc, expect: g.expect ?? null, logged: mine.length, backfilled: mine.filter((r) => r.backfilled).length,
               weeks: Array.from(new Set(mine.map((r) => r.week))).length, horizons: byH, horizons_univ: byU };
    });
    const recent = rows.filter((r) => r.ex[28] != null).slice(0, 40).map((r) => ({
      week: r.week, kind: r.kind, symbol: r.symbol, backfilled: r.backfilled,
      watched: r.kind === "insider_buy" ? !!r.detail.watched : null,
      ret_28d: r.ret[28], ex_28d: r.ex[28], ex_84d: r.ex[84], exu_28d: r.exU[28], exu_84d: r.exU[84],
    }));
    const weeks = Array.from(new Set(rows.map((r) => r.week))).sort();
    return NextResponse.json({ market, first_week: weeks[0] ?? null, last_week: weeks[weeks.length - 1] ?? null, groups, recent });
  } catch {
    return NextResponse.json({ market, first_week: null, last_week: null, groups: [], recent: [] });
  }
}
