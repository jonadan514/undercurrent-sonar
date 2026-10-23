"use client";

// 테마 흐름 이력 (2026-10-05) - 테마 하나의 세 축이 주별로 어떻게 움직여 왔는지와, 최근 흐름을 만든 기업.
// 레이더는 "이번 주 한 칸"만 보여서 실적 -> 주가 -> 뉴스 순서가 실제로 일어나는지 볼 수 없었다.
// 세 축은 합치지 않고 한 줄씩 둔다(원칙 1). 계산 불가(na)는 하락처럼 칠하지 않는다(원칙 4).

import PageIntro from "@/src/components/PageIntro";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import StockLink from "@/src/components/StockLink";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { themeName } from "@/src/lib/themeNames";
import { krStockName } from "@/src/lib/krStockNames";
import { useMarket } from "@/src/contexts/MarketContext";
import { ObservationCard, ObservationForm, ObservationT } from "@/src/components/Observation";
import { labelWithKo } from "@/src/lib/labelNames";

const GOOD = "var(--good)";
const DANGER = "var(--danger)";
const MUTED = "var(--text-muted)";
const FAINT = "var(--text-faint)";
const ACCENT = "var(--accent)";
const INFO = "var(--info)";
const MONO = 'ui-monospace, "SF Mono", "Cascadia Code", "Roboto Mono", monospace';
const WEEKS = 12;

type Arrow = "up2" | "up1" | "flat" | "down" | "na" | null;

interface WeekRow {
  week_start: string;
  news_count: number | null;
  news_baseline: number | null;
  news_ratio: number | null;
  news_arrow: Arrow;
  earn_members: number | null;
  earn_improved: number | null;
  earn_insufficient: number | null;
  earn_ratio: number | null;
  earn_arrow: Arrow;
  earn_as_of: string | null;
  price_median_ret: number | null;
  price_index_ret: number | null;
  price_excess: number | null;
  price_arrow: Arrow;
  label: string | null;
  member_count: number | null;
}

interface MemberRow {
  ticker: string;
  linkage: string | null;
  price_ret: number | null;
  rev_yoy: number | null;
  rev_quarter: string | null;
  earn_status: string | null;
  om_now?: number | null;
  om_change?: number | null;
  om_status?: string | null;
  surprise?: { pct: number; date: string; estimate: number | null; reported: number | null } | null;
  facts?: { analysts: number | null; from_high: number | null; from_low: number | null; as_of: string | null } | null;
  wl_name: string | null;
  valuation_tier: string | null;
  growth_tier: string | null;
  in_watchlist: number;
}

interface History {
  weeks: WeekRow[];
  members: MemberRow[];
  members_week: string | null;
  member_counts: { business: number; perceived: number; peripheral: number } | null;
  news_source_switch_week: string;
}

const LABEL_SHORT: Record<string, string> = {
  "Quiet Strength": "QS", "Quiet Recovery": "QR", "Early Buzz": "EB",
  "Overheated Buzz": "OB", "Full Alignment": "FA", "Full Decline": "FD",
};
const LABEL_COLOR: Record<string, string> = {
  "Quiet Strength": ACCENT, "Quiet Recovery": ACCENT, "Early Buzz": INFO,
  "Overheated Buzz": INFO, "Full Alignment": "var(--text-secondary)", "Full Decline": "var(--text-secondary)",
};
const AXES = [
  { key: "news_arrow", label: "뉴스" },
  { key: "earn_arrow", label: "실적" },
  { key: "price_arrow", label: "주가" },
] as const;

const isUp = (a: Arrow) => a === "up1" || a === "up2";
function glyph(a: Arrow): string {
  return a === "up2" ? "↑↑" : a === "up1" ? "↑" : a === "flat" ? "→" : a === "down" ? "↓" : "–";
}
function color(a: Arrow): string {
  return isUp(a) ? GOOD : a === "down" ? DANGER : a === "flat" ? MUTED : FAINT;
}
function pct(n: number | null | undefined, digits = 1): string {
  if (n == null) return "-";
  return `${n >= 0 ? "+" : ""}${(n * 100).toFixed(digits)}%`;
}
function md(day: string): string {
  const [, m, d] = day.split("-");
  return `${Number(m)}/${Number(d)}`;
}
/** 최근 주로 끝나는 WEEKS개의 연속된 월요일 - 행이 없는 주도 칸을 비워 둔다(9/21처럼 빠진 주가 보이게). */
function weekGrid(latest: string, n: number): string[] {
  const out: string[] = [];
  const base = new Date(`${latest}T00:00:00Z`);
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(base);
    d.setUTCDate(d.getUTCDate() - 7 * i);
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}

function cellTitle(axis: string, r: WeekRow | undefined): string {
  if (!r) return "이 주 데이터 없음";
  if (axis === "news_arrow")
    return r.news_count == null ? "뉴스 건수 없음(수집 실패 또는 기준선 쌓는 중)"
      : `뉴스 ${r.news_count}건 / 기준선 ${r.news_baseline != null ? Math.round(r.news_baseline) : "-"}건`;
  if (axis === "earn_arrow")
    return r.earn_members == null ? "실적 데이터 없음"
      : `${r.earn_members}개사 중 ${r.earn_improved ?? 0}개 매출 성장률이 시장 중앙값 초과` +
        (r.earn_insufficient ? ` (데이터부족 ${r.earn_insufficient})` : "") + (r.earn_as_of ? ` · ${r.earn_as_of}` : "");
  return r.price_median_ret == null ? "주가 데이터 없음"
    : `소속 중앙값 ${pct(r.price_median_ret)} · 지수 대비 ${pct(r.price_excess)}p (4주)`;
}

/** 축 하나의 최근 움직임을 사실로만 요약한다 - 예측하지 않는다. */
// 계산이 없는 주(행 자체가 없음, 예: 9/21)는 건너뛰고 센다 - 모르는 주를 "끊김"으로 보지 않는다.
// startIdx는 grid 위치(주 간격 비교용).
function axisSummary(grid: string[], byWeek: Record<string, WeekRow>, key: (typeof AXES)[number]["key"]) {
  const idx = grid.map((_, i) => i).filter((i) => byWeek[grid[i]]);
  const arrows = idx.map((i) => (byWeek[grid[i]][key] ?? null) as Arrow);
  if (arrows.length === 0) return { text: "데이터 없음", startIdx: -1, up: false };
  const last = arrows[arrows.length - 1];
  if (isUp(last)) {
    let j = arrows.length - 1;
    while (j > 0 && isUp(arrows[j - 1])) j--;
    return { text: `↑ ${arrows.length - j}주째 (${md(grid[idx[j]])} 주부터)`, startIdx: idx[j], up: true };
  }
  const lastUp = arrows.map(isUp).lastIndexOf(true);
  const lastUpTxt = lastUp >= 0 ? `마지막 ↑ ${md(grid[idx[lastUp]])} 주` : null;
  if (last == null || last === "na")
    return { text: lastUpTxt ? `이번 주 데이터 부족 · ${lastUpTxt}` : "데이터 부족", startIdx: -1, up: false };
  return { text: lastUpTxt ? `지금 ${glyph(last)} · ${lastUpTxt}` : `${WEEKS}주 동안 ↑ 없음`, startIdx: -1, up: false };
}

function Sparkline({ values, format }: { values: (number | null)[]; format: (v: number) => string }) {
  const W = 600, H = 56, P = 4;
  const nums = values.filter((v): v is number => v != null);
  if (nums.length < 2) return <div className="text-[12px]" style={{ color: FAINT }}>값이 2주 이상 있어야 그립니다</div>;
  const min = Math.min(...nums), max = Math.max(...nums);
  const span = max - min || 1;
  const x = (i: number) => P + (i * (W - 2 * P)) / (values.length - 1);
  const y = (v: number) => H - P - ((v - min) * (H - 2 * P)) / span;
  const seg = (from: number, to: number) => values
    .map((v, i) => (v == null || i < from || i > to ? null : `${x(i)},${y(v)}`))
    .filter(Boolean).join(" ");
  const lastIdx = values.length - 1 - [...values].reverse().findIndex((v) => v != null);
  return (
    <div className="flex items-center gap-3">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-14 w-full" preserveAspectRatio="none" role="img">
        <polyline points={seg(0, values.length - 1)} fill="none" stroke={ACCENT} strokeWidth="2" vectorEffect="non-scaling-stroke" />
        {min < 0 && max > 0 && <line x1={0} x2={W} y1={y(0)} y2={y(0)} stroke="var(--border-ctrl)" strokeWidth="1" vectorEffect="non-scaling-stroke" />}
      </svg>
      <span className="w-20 shrink-0 text-right text-[12px]" style={{ fontFamily: MONO, color: "var(--text-primary)" }}>
        {values[lastIdx] != null ? format(values[lastIdx] as number) : "-"}
      </span>
    </div>
  );
}

const EARN_STATUS: Record<string, { text: string; color: string }> = {
  improved: { text: "중앙값 초과", color: GOOD },
  not_improved: { text: "미달", color: MUTED },
  insufficient: { text: "데이터부족", color: FAINT },
};

function ThemeHistory() {
  const params = useSearchParams();
  const router = useRouter();
  const themeId = params.get("id") ?? "";
  const market = params.get("market") === "KR" ? "KR" : "US";
  // 시장은 주소(market=)가 기준이고, 화면 위 공용 시장 탭(PageMarketTabs)과 맞춘다:
  // 처음 열 때 공용 탭을 주소 값으로 맞추고, 그 뒤 공용 탭을 누르면 주소를 바꾼다.
  const { market: ctxMarket, setMarket: setCtxMarket } = useMarket();
  const synced = useRef(false);
  useEffect(() => {
    if (!synced.current) {
      synced.current = true;
      if (ctxMarket !== market) setCtxMarket(market);
      return;
    }
    if (ctxMarket !== market && themeId)
      router.replace(`/radar/theme?id=${encodeURIComponent(themeId)}&market=${ctxMarket}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ctxMarket]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<History | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAll, setShowAll] = useState(false);
  const [notes, setNotes] = useState<ObservationT[]>([]);
  const [noteWeek, setNoteWeek] = useState<string | undefined>();
  const [writing, setWriting] = useState(false);
  const loadNotes = useMemo(() => () => {
    if (!themeId) return;
    fetch(`/api/notes?kind=theme&theme_id=${encodeURIComponent(themeId)}&market=${market}`)
      .then((r) => r.json())
      .then((d) => { setNotes(Array.isArray(d.observations) ? d.observations : []); setNoteWeek(d.current_week); })
      .catch(() => setNotes([]));
  }, [themeId, market]);
  useEffect(() => { loadNotes(); }, [loadNotes]);

  useEffect(() => {
    if (!themeId) return;
    setLoading(true);
    fetch(`/api/radar/theme-history?theme_id=${encodeURIComponent(themeId)}&market=${market}&weeks=${WEEKS}`)
      .then((r) => r.json())
      .then((d) => setData(d && Array.isArray(d.weeks) ? d : null))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [themeId, market]);

  const { ko, en } = themeName(themeId);
  const weeks = data?.weeks ?? [];
  const latest = weeks.length ? weeks[weeks.length - 1] : null;
  const grid = useMemo(() => (latest ? weekGrid(latest.week_start, WEEKS) : []), [latest]);
  const byWeek = useMemo(() => Object.fromEntries(weeks.map((w) => [w.week_start, w])), [weeks]);
  const switchIdx = data ? grid.indexOf(data.news_source_switch_week) : -1;

  const summaries = AXES.map((a) => ({ ...a, ...axisSummary(grid, byWeek, a.key) }));
  const earnS = summaries[1], priceS = summaries[2];
  let order: string | null = null;
  if (earnS.up && priceS.up) {
    const gap = priceS.startIdx - earnS.startIdx;
    order = gap > 0 ? `지금 이어지는 ↑를 기준으로 실적이 주가보다 ${gap}주 먼저 시작됐다`
      : gap < 0 ? `지금 이어지는 ↑를 기준으로 주가가 실적보다 ${-gap}주 먼저 시작됐다`
      : "지금 이어지는 ↑는 실적과 주가가 같은 주에 시작됐다";
  }

  const members = [...(data?.members ?? [])].sort((a, b) => (b.price_ret ?? -Infinity) - (a.price_ret ?? -Infinity));
  const shown = showAll ? members : members.slice(0, 10);
  const omCounts = members.reduce((acc, m) => {
    if (m.om_status) acc[m.om_status] = (acc[m.om_status] ?? 0) + 1;
    return acc;
  }, {} as Record<string, number>);
  const hasMargin = members.some((m) => m.om_status != null || m.om_now != null);
  const withSurprise = members.filter((m) => m.surprise);
  const hasFacts = members.some((m) => m.facts && (m.facts.analysts != null || m.facts.from_high != null));
  const factsAsOf = members.map((m) => m.facts?.as_of).filter(Boolean).sort().pop();
  const surpriseBeat = withSurprise.filter((m) => (m.surprise?.pct ?? 0) > 0).length;
  const earnCounts = members.reduce((acc, m) => {
    const k = m.earn_status ?? "insufficient";
    acc[k] = (acc[k] ?? 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  // 좁은 화면에서 타임라인이 가로로 넘치면 최근 주가 보이게 오른쪽 끝에서 시작
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [grid]);
  const box = "rounded-2xl p-4 md:p-5";
  const boxStyle = { background: "var(--bg-card)", border: "1px solid var(--border)" };

  if (!themeId) return <div className="py-16 text-center" style={{ color: MUTED }}>테마가 지정되지 않았습니다. <Link href="/radar" className="underline">테마 레이더로</Link></div>;

  return (
    <div className="mx-auto w-full max-w-[1280px] space-y-4 pb-10">
      {/* 머리 */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <Link href="/radar" className="text-[12px]" style={{ color: MUTED }}>← 테마 레이더</Link>
          <h1 className="mt-1 text-[20px] sm:text-[22px] font-bold" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>{ko}</h1>
          <p className="text-[12px]" style={{ color: FAINT }}>{en} · {market === "US" ? "미국" : "한국"} · 흐름 이력 {WEEKS}주</p>
        </div>
      </div>
      <PageIntro k="radar_theme" />

      {loading ? (
        <div className="py-16 text-center" style={{ color: MUTED }}>불러오는 중...</div>
      ) : !data || weeks.length === 0 ? (
        <div className={box} style={boxStyle}>
          <p style={{ color: MUTED }}>이 시장에는 이 테마의 주간 신호가 없습니다(소속 기업이 없거나 아직 계산 전).</p>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px]" style={{ color: MUTED }}>
            {data.member_counts && (
              <span>사업 소속 <b style={{ color: "var(--text-primary)" }}>{data.member_counts.business}</b>개사
                {data.member_counts.perceived > 0 && <> · 시장 인식 {data.member_counts.perceived}개사</>}
                {data.member_counts.peripheral > 0 && <> · 간접 {data.member_counts.peripheral}개사</>}
              </span>
            )}
            <span>기준 {md(latest!.week_start)} 주</span>
            <span>이번 주 라벨 {latest!.label ? <b style={{ color: LABEL_COLOR[latest!.label] ?? ACCENT }}>{labelWithKo(latest!.label)}</b> : "없음"}</span>
          </div>

          {/* ① 세 축 타임라인 */}
          <section className={box} style={boxStyle}>
            <h2 className="mb-3 text-[15px] font-bold" style={{ color: "var(--text-primary)" }}>세 축 타임라인</h2>
            <div ref={scrollRef} className="overflow-x-auto">
              <table className="w-full border-collapse text-center" style={{ minWidth: 640 }}>
                <thead>
                  <tr>
                    <th className="w-14" />
                    {grid.map((w, i) => (
                      <th key={w} className="pb-2 text-[11px] font-normal whitespace-nowrap"
                        style={{ color: i === grid.length - 1 ? "var(--text-primary)" : FAINT,
                                 borderLeft: i === switchIdx ? "1px dashed var(--border-ctrl)" : undefined }}>
                        {md(w)}
                        {notes.some((n) => n.week_start === w) && <span title="이 주에 남긴 관찰" style={{ color: ACCENT }}> ✎</span>}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {AXES.map((a) => (
                    <tr key={a.key}>
                      <td className="py-1.5 pr-2 text-left text-[12px] whitespace-nowrap" style={{ color: MUTED }}>{a.label}</td>
                      {grid.map((w, i) => {
                        const r = byWeek[w];
                        const ar = (r?.[a.key] ?? null) as Arrow;
                        return (
                          <td key={w} title={`${md(w)} 주 · ${cellTitle(a.key, r)}`} className="py-1.5 text-[15px] font-bold"
                            style={{ color: r ? color(ar) : "var(--border-ctrl)", fontFamily: MONO,
                                     borderLeft: i === switchIdx ? "1px dashed var(--border-ctrl)" : undefined }}>
                            {r ? glyph(ar) : "·"}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                  <tr>
                    <td className="py-1.5 pr-2 text-left text-[12px]" style={{ color: MUTED }}>라벨</td>
                    {grid.map((w, i) => {
                      const l = byWeek[w]?.label;
                      return (
                        <td key={w} title={l ?? "라벨 없음"} className="py-1.5 text-[11px] font-bold"
                          style={{ color: l ? LABEL_COLOR[l] ?? ACCENT : "var(--border-ctrl)", fontFamily: MONO,
                                   borderLeft: i === switchIdx ? "1px dashed var(--border-ctrl)" : undefined }}>
                          {l ? LABEL_SHORT[l] ?? "●" : "·"}
                        </td>
                      );
                    })}
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-[12px] leading-relaxed" style={{ color: FAINT }}>
              ↑↑ 크게 오름 · ↑ 오름 · → 보합 · ↓ 내림 · – 데이터 부족(탈락 아님) · · 그 주 계산 없음. 칸에 마우스를 올리면 숫자가 보입니다.
              {switchIdx >= 0 && <> 점선은 뉴스 수집원이 바뀐 주로, 그 앞뒤 뉴스 건수는 비교할 수 없습니다. 뉴스 축은 바뀐 뒤 4주가 쌓여야 다시 판정됩니다.</>}
              {" "}라벨 약자: QS Quiet Strength · QR Quiet Recovery · EB Early Buzz · OB Overheated Buzz · FA Full Alignment · FD Full Decline.
            </p>
          </section>

          {/* ② 먼저 움직인 축 */}
          <section className={box} style={boxStyle}>
            <h2 className="mb-3 text-[15px] font-bold" style={{ color: "var(--text-primary)" }}>최근 움직임</h2>
            <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
              {summaries.map((s) => (
                <div key={s.key} className="rounded-lg px-3 py-2 text-[13px]" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                  <span style={{ color: MUTED }}>{s.label}</span>{" "}
                  <b style={{ color: s.up ? GOOD : "var(--text-primary)" }}>{s.text}</b>
                </div>
              ))}
            </div>
            {order && <p className="mt-3 text-[13px]" style={{ color: "var(--text-secondary)" }}>{order}</p>}
            <p className="mt-2 text-[12px]" style={{ color: FAINT }}>지난 {WEEKS}주에 일어난 일만 적습니다. 앞으로 어떻게 될지는 판단하지 않습니다.</p>
          </section>

          {/* ③ 숫자 추이 */}
          <section className={box} style={boxStyle}>
            <h2 className="mb-3 text-[15px] font-bold" style={{ color: "var(--text-primary)" }}>숫자 추이</h2>
            <div className="space-y-3">
              <div>
                <p className="mb-1 text-[12px]" style={{ color: MUTED }}>뉴스 건수 (주){switchIdx > 0 && ` - 수집원이 바뀐 ${md(grid[switchIdx])} 주부터만(그 전 건수는 다른 출처라 같은 눈금에 그리지 않음)`}</p>
                <Sparkline values={grid.map((w, i) => (switchIdx > 0 && i < switchIdx ? null : byWeek[w]?.news_count ?? null))} format={(v) => `${v}건`} />
              </div>
              <div>
                <p className="mb-1 text-[12px]" style={{ color: MUTED }}>실적: 매출 성장률이 시장 중앙값을 넘은 소속 기업 비율</p>
                <Sparkline values={grid.map((w) => byWeek[w]?.earn_ratio ?? null)} format={(v) => `${Math.round(v * 100)}%`} />
              </div>
              <div>
                <p className="mb-1 text-[12px]" style={{ color: MUTED }}>주가: 소속 중앙값의 지수 대비 초과수익 (4주)</p>
                <Sparkline values={grid.map((w) => byWeek[w]?.price_excess ?? null)} format={(v) => `${pct(v)}p`} />
              </div>
            </div>
          </section>

          {/* ④ 이번 흐름을 만든 기업 */}
          <section className={box} style={boxStyle}>
            <h2 className="mb-1 text-[15px] font-bold" style={{ color: "var(--text-primary)" }}>이번 흐름을 만든 기업</h2>
            {members.length === 0 ? (
              <p className="text-[13px]" style={{ color: MUTED }}>
                기업별 값은 2026-10-05부터 쌓입니다. 다음 주간 계산(주가·실적) 뒤에 채워집니다.
              </p>
            ) : (
              <>
                <p className="mb-3 text-[12px]" style={{ color: FAINT }}>
                  {data.members_week && `${md(data.members_week)} 주 · `}사업 소속(직접·부분) {members.length}개사 · 4주 수익률 높은 순 ·
                  실적 중앙값 초과 {earnCounts.improved ?? 0} / 미달 {earnCounts.not_improved ?? 0} / 데이터부족 {earnCounts.insufficient ?? 0}
                  {hasMargin && <> · 영업이익률(전년 같은 분기 대비) 개선 {omCounts["개선"] ?? 0} / 유지 {omCounts["유지"] ?? 0} / 악화 {omCounts["악화"] ?? 0}</>}
                  {withSurprise.length > 0 && <> · 최근 100일 실적 발표 {withSurprise.length}개사 중 추정치 상회 {surpriseBeat}</>}
                </p>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-[13px]" style={{ minWidth: hasFacts ? 900 : 560 }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--border)", color: MUTED }}>
                        <th className="py-2 text-left font-normal">종목</th>
                        <th className="py-2 text-right font-normal">4주 수익률</th>
                        <th className="py-2 text-right font-normal">매출 YoY</th>
                        <th className="py-2 text-left font-normal pl-4">실적</th>
                        {hasMargin && <th className="py-2 text-right font-normal" title="최근 분기 영업이익률과 1년 전 같은 분기 대비 차이 (±1%p 이상이면 개선/악화)">영업이익률</th>}
                        {withSurprise.length > 0 && <th className="py-2 pl-3 text-right font-normal" title="최근 100일 안에 발표한 실적의 EPS 추정치 대비 차이">서프라이즈</th>}
                        {hasFacts && <th className="py-2 pl-3 text-right font-normal" title="수집 시점 가격의 52주 고점 대비 거리">52주 고점 대비</th>}
                        {hasFacts && <th className="py-2 pl-3 text-right font-normal" title="이 종목을 다루는 애널리스트 수 - 적을수록 시장이 덜 보는 종목">애널리스트</th>}
                        <th className="py-2 pl-4 text-left font-normal">워치리스트</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shown.map((m) => {
                        const st = EARN_STATUS[m.earn_status ?? "insufficient"] ?? EARN_STATUS.insufficient;
                        const name = market === "KR" ? (krStockName(m.ticker) || m.wl_name) : m.wl_name;
                        return (
                          <tr key={m.ticker} style={{ borderBottom: "1px solid var(--border-dim)" }}>
                            <td className="py-2">
                              <StockLink market={market} symbol={m.ticker} className="font-bold" style={{ color: "var(--text-primary)" }}>{market === "KR" && name ? name : m.ticker}</StockLink>
                              {name && (
                                <span className="ml-1.5 text-[11px]" style={{ fontFamily: MONO, color: FAINT }}>
                                  {market === "KR" ? m.ticker : name}
                                </span>
                              )}
                              {m.linkage === "partial" && <span className="ml-1.5 text-[11px]" style={{ color: FAINT }}>부분</span>}
                            </td>
                            <td className="py-2 text-right" style={{ fontFamily: MONO, color: m.price_ret == null ? FAINT : m.price_ret >= 0 ? GOOD : DANGER }}>
                              {pct(m.price_ret)}
                            </td>
                            <td className="py-2 text-right" style={{ fontFamily: MONO, color: "var(--text-secondary)" }}>
                              {pct(m.rev_yoy)}{m.rev_quarter && <span className="ml-1 text-[10px]" style={{ color: FAINT }}>{m.rev_quarter.replace("-", " ")}</span>}
                            </td>
                            <td className="py-2 pl-4" style={{ color: st.color }}>{st.text}</td>
                            {hasMargin && (
                              <td className="py-2 text-right whitespace-nowrap" style={{ fontFamily: MONO }}
                                title={m.om_status ? `1년 전 같은 분기 대비 ${m.om_status}` : "데이터부족(분기 손익 부족)"}>
                                {m.om_now != null ? <span style={{ color: "var(--text-secondary)" }}>{(m.om_now * 100).toFixed(1)}%</span> : <span style={{ color: FAINT }}>-</span>}
                                {m.om_change != null && (
                                  <span className="ml-1 text-[11px]" style={{ color: m.om_status === "개선" ? GOOD : m.om_status === "악화" ? DANGER : MUTED }}>
                                    {m.om_change >= 0 ? "+" : ""}{(m.om_change * 100).toFixed(1)}%p
                                  </span>
                                )}
                              </td>
                            )}
                            {withSurprise.length > 0 && (
                              <td className="py-2 pl-3 text-right whitespace-nowrap" style={{ fontFamily: MONO }}
                                title={m.surprise ? `${m.surprise.date} 발표 · EPS 추정 ${m.surprise.estimate ?? "-"} → 실제 ${m.surprise.reported ?? "-"}` : "최근 100일 안 발표 없음"}>
                                {m.surprise ? (
                                  <>
                                    <span style={{ color: m.surprise.pct > 0 ? GOOD : m.surprise.pct < 0 ? DANGER : MUTED }}>
                                      {m.surprise.pct > 0 ? "+" : ""}{m.surprise.pct.toFixed(1)}%
                                    </span>
                                    <span className="ml-1 text-[10px]" style={{ color: FAINT }}>{md(m.surprise.date)}</span>
                                  </>
                                ) : <span style={{ color: FAINT }}>-</span>}
                              </td>
                            )}
                            {hasFacts && (
                              <td className="py-2 pl-3 text-right whitespace-nowrap" style={{ fontFamily: MONO, color: "var(--text-secondary)" }}
                                title={m.facts?.from_low != null ? `52주 저점 대비 ${pct(m.facts.from_low)}` : undefined}>
                                {m.facts?.from_high != null ? pct(m.facts.from_high) : <span style={{ color: FAINT }}>-</span>}
                              </td>
                            )}
                            {hasFacts && (
                              <td className="py-2 pl-3 text-right whitespace-nowrap" style={{ fontFamily: MONO, color: "var(--text-secondary)" }}>
                                {m.facts?.analysts != null ? `${m.facts.analysts}명` : <span style={{ color: FAINT }}>-</span>}
                              </td>
                            )}
                            <td className="py-2 pl-4 text-[12px]" style={{ color: m.in_watchlist ? ACCENT : FAINT }}>
                              {m.in_watchlist ? `후보${m.valuation_tier ? ` · ${m.valuation_tier}` : ""}${m.growth_tier ? ` · ${m.growth_tier}` : ""}` : "-"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {members.length > 10 && (
                  <button onClick={() => setShowAll((v) => !v)} className="mt-2 text-[12px]" style={{ color: MUTED }}>
                    {showAll ? "접기" : `전체 ${members.length}개사 보기`}
                  </button>
                )}
                <p className="mt-2 text-[12px]" style={{ color: FAINT }}>
                  워치리스트 "후보"는 재무 함정 필터를 통과한 종목입니다. 실적 판정은 테마 실적 축과 같은 기준(시장 유니버스 매출 성장률 중앙값)입니다.
                  {hasMargin && " 영업이익률은 최근 분기를 1년 전 같은 분기와 비교한 참고 값으로, 실적 축 계산에는 들어가지 않습니다."}
                  {hasFacts && ` 52주 고점 대비·애널리스트 수는 워치리스트 스크리닝 때 받은 기업 정보 기준${factsAsOf ? `(${md(factsAsOf)})` : ""}입니다.`}
                </p>
              </>
            )}
          </section>

          {/* ⑤ 관찰 노트 */}
          <section className={box} style={boxStyle}>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h2 className="text-[15px] font-bold" style={{ color: "var(--text-primary)" }}>관찰 노트</h2>
              <Link href="/notes" className="text-[12px]" style={{ color: MUTED }}>전체 노트 →</Link>
              <button onClick={() => setWriting(true)} className="ml-auto rounded-lg px-3 py-1.5 text-[13px] font-bold" style={{ background: ACCENT, color: "#000" }}>
                관찰 남기기
              </button>
            </div>
            {notes.length === 0 ? (
              <p className="text-[13px]" style={{ color: FAINT }}>
                이 테마에 남긴 관찰이 없습니다. 지금 보이는 흐름에 대한 가설을 한 줄 남기면 4주·12주 뒤 그때와 지금이 나란히 붙습니다.
              </p>
            ) : (
              <div className="space-y-3">
                {notes.map((o) => <ObservationCard key={o.id} o={o} currentWeek={noteWeek} onChanged={loadNotes} showTarget={false} />)}
              </div>
            )}
          </section>
          {writing && (
            <ObservationForm kind="theme" market={market} themeId={themeId} title={ko} onClose={() => setWriting(false)} onSaved={loadNotes} />
          )}
        </>
      )}
    </div>
  );
}

export default function ThemeHistoryPage() {
  return (
    <Suspense fallback={<div className="py-16 text-center" style={{ color: MUTED }}>불러오는 중...</div>}>
      <ThemeHistory />
    </Suspense>
  );
}
