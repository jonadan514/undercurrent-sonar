// 이번 주 이유(2026-11-07 워치리스트 '이번 주 볼 후보', 2026-11-15 공용으로 옮김) - 최신 주간 브리핑 칸에서 종목별 이유를 모은다.
// 이유를 그대로 칩으로 보여 줄 뿐 점수·순위가 아니다(원칙 1). 규칙은 src/analyzers/week_focus.py week_reasons와 같아야 한다.
export type WeekSignals = Map<string, string[]>;
export function weekSignalsFrom(b: Record<string, unknown> | null): WeekSignals {
  const out: WeekSignals = new Map();
  if (!b) return out;
  const add = (m: string | undefined, s: string | undefined, why: string) => {
    if (!m || !s) return;
    const k = `${m}:${s}`;
    const cur = out.get(k) ?? [];
    if (!cur.includes(why)) out.set(k, [...cur, why]);
  };
  type G = { market?: string; symbol?: string; buyers?: number; all_plan?: boolean; pct?: number | null; warn?: boolean };
  const ins = (b.insider_week ?? {}) as { items?: G[]; discovery?: G[] };
  for (const g of [...(ins.items ?? []), ...(ins.discovery ?? [])]) if (!g.all_plan) add(g.market, g.symbol, (g.buyers ?? 0) > 1 ? "내부자 여러 명 매수" : "내부자 매수");
  const kd = (b.kr_disclosures ?? {}) as Record<string, { items?: G[] } | undefined>;
  for (const x of kd.contract?.items ?? []) if ((x.pct ?? 0) >= 10) add("KR", x.symbol, "큰 공급계약");
  for (const x of kd.termination?.items ?? []) add("KR", x.symbol, "계약 해지");
  for (const x of ((b.us_8k_week ?? {}) as { items?: G[] }).items ?? []) if (x.warn) add("US", x.symbol, "8-K 주의");
  for (const x of ((b.turnaround ?? {}) as { added?: G[] }).added ?? []) add(x.market, x.symbol, "실적 반전 신규");
  return out;
}


/** 테마 화면 등 후보 정보가 따로 없는 곳용 - 브리핑의 신규 통과(added_keys)·관심도 HOT 진입까지 더한다(워치리스트는 후보 행에서 따로 본다). */
export function weekReasonsAll(b: Record<string, unknown> | null): WeekSignals {
  const out = weekSignalsFrom(b);
  if (!b) return out;
  const add = (k: string, why: string) => { const cur = out.get(k) ?? []; if (!cur.includes(why)) out.set(k, [why, ...cur]); };
  for (const k of ((b.watchlist ?? {}) as { added_keys?: string[] }).added_keys ?? []) add(k, "신규 통과");
  for (const x of (b.sentiment_heating ?? []) as { market?: string; symbol?: string; path?: string }[])
    if (x.market && x.symbol && String(x.path ?? "").endsWith("HOT")) add(`${x.market}:${x.symbol}`, "관심도 HOT 진입");
  return out;
}
