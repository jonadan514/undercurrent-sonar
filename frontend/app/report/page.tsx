"use client";

import { Suspense, useEffect, useState, type ReactNode } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import FlagIcon from "@/src/components/FlagIcon";
import StockLink from "@/src/components/StockLink";
import PageHeader from "@/src/components/PageHeader";
import EmptyState from "@/src/components/EmptyState";
import { Section } from "@/src/components/Section";
import { krStockName } from "@/src/lib/krStockNames";

// 월간 리서치 보고서(2026-11-07). scripts/generate_monthly_report.py가 매달 첫 월요일에 지난달 것을 monthly_reports에 쌓는다.
// 사이트에 이미 있는 것(세 축 신호·시장 환경·테마 뉴스·가치사슬·워치리스트 스냅샷·관찰 노트·실적 일정)을 한 달 단위로 묶은 읽을거리 -
// 새 점수·등급은 없다(원칙 1). 이달 요약만 GPT가 쓰고 숫자는 쓰지 않는다(원칙 2). 인쇄하면 종이 색으로(globals.css @media print).

type Mk = "US" | "KR";
interface RegimeWeek { week: string; as_of: string; combos: string[] }
interface LabelWeek { week: string; label: string; label_ko: string }
interface ThemeRow { theme_id: string; theme: string; market: Mk; last: { news: string | null; earn: string | null; price: string | null };
                     labels?: LabelWeek[]; from?: string; to?: string }
interface Article { title: string; url: string; source: string; published_at: string }
interface NewsBlock { theme_id: string; theme: string; market: Mk; articles: Article[]; total: number }
interface MapItem { symbol: string; name: string; linkage: string; rev_yoy: number | null; earn_status: string | null; events: string[] }
interface MapTheme { theme_id: string; theme: string; market: Mk; groups: { n: number; label: string; items: MapItem[] }[] }
interface Ref { market: Mk; symbol: string; name: string }
interface Change { from: string; to: string; start_total: number; end_total: number; added: Ref[]; added_count: number; removed: Ref[]; removed_count: number }
interface Review { kind: string; market: Mk; target: string; checkpoint: string; created_at: string; results: { key?: string; expect: string; hit: boolean | null }[] }
interface CalItem { date: string; market: Mk; symbol: string; name: string; estimate: boolean; tags: string[] }
interface Report {
  month: string; generated_at: string; weeks: string[]; briefing_weeks: string[];
  summary: string;
  regime: Partial<Record<Mk, RegimeWeek[]>>;
  themes: { labeled: ThemeRow[]; earn_turns: ThemeRow[] };
  news: NewsBlock[];
  company_map: MapTheme[];
  watchlist: { watchlist: Change | null; turnaround: Change | null };
  month_events?: { market: Mk; symbol: string; name: string; events: string[] }[];   // 2026-11-07 둘째 판부터
  reviews: Review[];
  calendar: { earnings: CalItem[]; earnings_total: number; deadlines: { date: string; what: string }[] };
}

const MK_KO: Record<Mk, string> = { US: "미국", KR: "한국" };
const ARROW: Record<string, { t: string; c: string }> = {
  up2: { t: "크게 오름", c: "var(--good)" }, up1: { t: "오름", c: "var(--good)" }, flat: { t: "보합", c: "var(--text-muted)" },
  down: { t: "내림", c: "var(--danger)" }, na: { t: "판단 불가", c: "var(--text-faint)" },
};
const EARN_DOT: Record<string, { t: string; c: string }> = {
  improved: { t: "실적 중앙값 초과", c: "var(--good)" }, not_improved: { t: "실적 미달", c: "var(--text-muted)" },
  insufficient: { t: "실적 데이터 부족", c: "var(--text-faint)" },
};
const MUTED = { color: "var(--text-muted)" };
const FAINT = { color: "var(--text-faint)" };

// 보고서를 만들 때 이름을 못 찾은 한국 종목(이름 = 코드)은 화면의 한국 종목 이름표로 한 번 더
const nameOf = (m: Mk, symbol: string, name: string) => (m === "KR" && (!name || name === symbol) ? krStockName(symbol) : name || symbol);
const md = (d: string) => { const [, m, dd] = d.split("-"); return `${Number(m)}/${Number(dd)}`; };
const monthKo = (m: string) => { const [y, mm] = m.split("-"); return `${y}년 ${Number(mm)}월`; };

function MkTag({ m }: { m: Mk }) {
  return <span className="inline-flex items-center gap-1 text-[12px]" style={MUTED}><FlagIcon market={m} size={13} />{MK_KO[m]}</span>;
}
function Arrow({ a }: { a: string | null | undefined }) {
  const x = ARROW[a ?? "na"] ?? ARROW.na;
  return <span style={{ color: x.c }}>{x.t}</span>;
}
function Chip({ children, tone }: { children: ReactNode; tone?: "accent" | "warn" }) {
  const c = tone === "accent" ? "var(--accent)" : tone === "warn" ? "var(--orange)" : "var(--text-secondary)";
  return <span className="inline-block rounded px-1.5 py-px text-[11.5px] whitespace-nowrap" style={{ border: `1px solid ${c}55`, color: c }}>{children}</span>;
}
function Sub({ children }: { children: ReactNode }) {
  return <h3 className="mb-1.5 mt-3 text-[13px] font-bold first:mt-0" style={{ color: "var(--text-primary)" }}>{children}</h3>;
}

function RegimeBlock({ r, weeks }: { r: Report["regime"]; weeks: string[] }) {
  const mks = (["US", "KR"] as Mk[]).filter((m) => (r[m] ?? []).length);
  if (!mks.length) return <p className="text-[13px]" style={MUTED}>이달 시장 환경 기록이 없습니다.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr style={MUTED}>
            <th className="py-1 pr-3 text-left font-normal">시장</th>
            {weeks.map((w) => <th key={w} className="py-1 pr-3 text-left font-normal whitespace-nowrap">{md(w)} 주</th>)}
          </tr>
        </thead>
        <tbody>
          {mks.map((m) => {
            const by = new Map((r[m] ?? []).map((x) => [x.week, x]));
            return (
              <tr key={m} style={{ borderTop: "1px solid var(--border-dim)" }}>
                <td className="py-1.5 pr-3"><MkTag m={m} /></td>
                {weeks.map((w) => {
                  const x = by.get(w);
                  return (
                    <td key={w} className="py-1.5 pr-3 align-top">
                      {!x ? <span style={FAINT}>-</span> : x.combos.length ? (
                        <span className="flex flex-wrap gap-1">{x.combos.map((c) => <Chip key={c} tone="accent">{c}</Chip>)}</span>
                      ) : <span style={FAINT}>뚜렷한 조합 없음</span>}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-1.5 text-[12px]" style={FAINT}>조합은 금리·환율·변동성 같은 축이 각자 지난 1년에 비해 어디쯤인지로 정해진 이름만 붙입니다(점수 없음). 축별 자세한 값은 개요의 시장 환경 칸.</p>
    </div>
  );
}

function ThemeFlow({ t, weeks }: { t: Report["themes"]; weeks: string[] }) {
  return (
    <>
      <Sub>라벨이 붙은 테마</Sub>
      {!t.labeled.length ? <p className="text-[13px]" style={MUTED}>이달 라벨이 붙은 테마가 없습니다.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr style={MUTED}>
                <th className="py-1 pr-3 text-left font-normal">테마</th>
                {weeks.map((w) => <th key={w} className="py-1 pr-3 text-left font-normal whitespace-nowrap">{md(w)} 주</th>)}
                <th className="py-1 pr-3 text-left font-normal whitespace-nowrap">월말 기준 뉴스 · 실적 · 주가</th>
              </tr>
            </thead>
            <tbody>
              {t.labeled.map((x) => {
                const by = new Map((x.labels ?? []).map((l) => [l.week, l]));
                return (
                  <tr key={`${x.market}:${x.theme_id}`} style={{ borderTop: "1px solid var(--border-dim)" }}>
                    <td className="py-1.5 pr-3 whitespace-nowrap">
                      <a href={`/radar/theme?id=${encodeURIComponent(x.theme_id)}&market=${x.market}`} className="font-bold hover:underline" style={{ color: "var(--text-primary)" }}>{x.theme}</a>
                      <span className="ml-1.5"><MkTag m={x.market} /></span>
                    </td>
                    {weeks.map((w) => <td key={w} className="py-1.5 pr-3">{by.get(w) ? <Chip tone="accent">{by.get(w)!.label_ko || by.get(w)!.label}</Chip> : <span style={FAINT}>-</span>}</td>)}
                    <td className="py-1.5 pr-3 whitespace-nowrap"><Arrow a={x.last.news} /> · <Arrow a={x.last.earn} /> · <Arrow a={x.last.price} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <Sub>실적 축이 바뀐 테마</Sub>
      {!t.earn_turns.length ? <p className="text-[13px]" style={MUTED}>이달 실적 축 방향이 바뀐 테마가 없습니다.</p> : (
        <ul className="space-y-1 text-[13px]">
          {t.earn_turns.map((x) => (
            <li key={`${x.market}:${x.theme_id}`}>
              <span className="font-bold" style={{ color: "var(--text-primary)" }}>{x.theme}</span> <MkTag m={x.market} />
              <span className="ml-2" style={MUTED}>소속 기업 실적: 월초</span> <Arrow a={x.from} /> <span style={MUTED}>→ 월말</span> <Arrow a={x.to} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function NewsBlocks({ news }: { news: NewsBlock[] }) {
  const has = news.filter((n) => n.articles.length);
  if (!has.length) return <p className="text-[13px]" style={MUTED}>이달 고른 기사가 없습니다.</p>;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {has.map((n) => (
        <div key={`${n.market}:${n.theme_id}`} className="print-avoid-break rounded-lg p-2.5" style={{ background: "var(--bg-inset)", border: "1px solid var(--border-dim)" }}>
          <div className="mb-1 flex items-baseline gap-2">
            <span className="text-[13px] font-bold" style={{ color: "var(--text-primary)" }}>{n.theme}</span><MkTag m={n.market} />
            <span className="ml-auto text-[11.5px]" style={FAINT}>이달 기사 {n.total.toLocaleString("ko-KR")}건 중</span>
          </div>
          <ul className="space-y-1">
            {n.articles.map((a) => (
              <li key={a.url} className="text-[13px] leading-snug">
                <a href={a.url} target="_blank" rel="noreferrer" className="hover:underline" style={{ color: "var(--text-secondary)" }}>{a.title}</a>
                <span className="ml-1.5 text-[11.5px]" style={FAINT}>{a.source}{a.published_at ? ` · ${md(a.published_at.slice(0, 10))}` : ""}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function CompanyMap({ maps }: { maps: MapTheme[] }) {
  if (!maps.length) return <p className="text-[13px]" style={MUTED}>이달 지도로 그릴 테마가 없습니다.</p>;
  return (
    <div className="space-y-4">
      {maps.map((t) => (
        <div key={`${t.market}:${t.theme_id}`} className="print-avoid-break">
          <div className="mb-1.5 flex items-baseline gap-2">
            <a href={`/radar/theme?id=${encodeURIComponent(t.theme_id)}&market=${t.market}`} className="text-[14px] font-bold hover:underline" style={{ color: "var(--text-primary)" }}>{t.theme}</a>
            <MkTag m={t.market} />
          </div>
          <div className="space-y-1.5">
            {t.groups.map((g) => (
              <div key={g.n} className="flex flex-col gap-1 sm:flex-row sm:gap-3">
                <div className="shrink-0 text-[12.5px] sm:w-44" style={g.n ? { color: "var(--text-secondary)" } : FAINT}>
                  {g.n ? `(${g.n}) ${g.label}` : g.label}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {!g.items.length && <span className="text-[12px]" style={FAINT}>-</span>}
                  {g.items.map((it) => {
                    const st = EARN_DOT[it.earn_status ?? "insufficient"] ?? EARN_DOT.insufficient;
                    return (
                      <span key={it.symbol} className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px]"
                        style={{ border: `1px solid ${it.events.length ? "var(--accent)" : "var(--border)"}`, color: "var(--text-secondary)" }}>
                        <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: st.c }} title={st.t} />
                        <StockLink market={t.market} symbol={it.symbol}>{nameOf(t.market, it.symbol, it.name)}</StockLink>
                        {it.linkage === "partial" && <span className="text-[10.5px]" style={FAINT} title="사업 일부만 이 테마에 해당">일부</span>}
                        {it.events.map((e) => <span key={e} className="text-[10.5px]" style={{ color: "var(--accent)" }}>{e}</span>)}
                      </span>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
      <p className="text-[12px]" style={FAINT}>
        구간은 가치사슬 순서(앞 → 뒤). 점 색은 월말 기준 실적 판정(초록 테마 중앙값보다 좋음 · 회색 못 미침 · 흐림 데이터 부족). &apos;일부&apos;는 사업 일부만 이 테마에 해당하는 기업. 테두리가 밝은 기업은 이달 공시·내부자 매수 같은 일이 있었던 곳.
      </p>
    </div>
  );
}

function ChangeBlock({ title, c }: { title: string; c: Change | null }) {
  if (!c) return <div className="text-[13px]"><Sub>{title}</Sub><p style={MUTED}>비교할 두 주가 없습니다.</p></div>;
  const names = (xs: Ref[], n: number) => (
    <span className="flex flex-wrap gap-x-2 gap-y-0.5">
      {xs.map((x) => <StockLink key={`${x.market}:${x.symbol}`} market={x.market} symbol={x.symbol} style={{ color: "var(--text-secondary)" }}>{nameOf(x.market, x.symbol, x.name)}</StockLink>)}
      {n > xs.length && <span style={FAINT}>{xs.length ? `외 ${n - xs.length}곳` : `${n}곳(이름 목록 없음)`}</span>}
      {!n && <span style={FAINT}>없음</span>}
    </span>
  );
  return (
    <div className="text-[13px]">
      <Sub>{title}</Sub>
      <p style={MUTED}>{md(c.from)} 주 {c.start_total}곳 → {md(c.to)} 주 {c.end_total}곳</p>
      <div className="mt-1 grid gap-1 sm:grid-cols-[6rem_1fr]">
        <span style={{ color: "var(--good)" }}>새로 든 곳 {c.added_count}</span>{names(c.added, c.added_count)}
        <span style={{ color: "var(--text-muted)" }}>빠진 곳 {c.removed_count}</span>{names(c.removed, c.removed_count)}
      </div>
    </div>
  );
}

// 관찰 노트 기대를 말로('뉴스↑' → '뉴스가 늘 것') - 기호만 있으면 무슨 기대였는지 한눈에 안 읽혔다(11/7)
const EXPECT_WORDS: Record<string, string> = {
  news_up: "뉴스가 늘 것", news_down: "뉴스가 줄 것", earn_up: "실적이 좋아질 것", earn_down: "실적이 나빠질 것",
  price_up: "주가가 오를 것", price_down: "주가가 내릴 것", earn_hold: "실적 개선이 이어질 것",
};
const EXPECT_BY_SYMBOL: Record<string, string> = { "뉴스↑": "news_up", "뉴스↓": "news_down", "실적↑": "earn_up", "실적↓": "earn_down",
  "주가↑": "price_up", "주가↓": "price_down", "실적↑ 유지": "earn_hold" };
const expectText = (x: { key?: string; expect: string }) => {
  const w = EXPECT_WORDS[x.key ?? EXPECT_BY_SYMBOL[x.expect] ?? ""];
  return w ? `'${w}'` : x.expect;
};

function Reviews({ rs }: { rs: Review[] }) {
  if (!rs.length) return <p className="text-[13px]" style={MUTED}>이달 회고 시점이 온 관찰 노트가 없습니다.</p>;
  return (
    <ul className="space-y-1 text-[13px]">
      {rs.map((r, i) => (
        <li key={i} className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-bold" style={{ color: "var(--text-primary)" }}>{r.target}</span><MkTag m={r.market} />
          <span style={FAINT}>{md(r.created_at)}에 적은 노트 · {r.checkpoint}주 뒤 확인</span>
          {r.results.length ? r.results.map((x) => (
            <span key={x.expect} style={{ color: x.hit ? "var(--good)" : x.hit === false ? "var(--orange)" : "var(--text-faint)" }}>
              {expectText(x)} → {x.hit ? "맞음" : x.hit === false ? "빗나감" : "판단 불가"}
            </span>
          )) : <span style={FAINT}>적어 둔 기대 없음</span>}
        </li>
      ))}
    </ul>
  );
}

function CalendarBlock({ c, month }: { c: Report["calendar"]; month: string }) {
  const by = new Map<string, CalItem[]>();
  for (const x of c.earnings) by.set(x.date, [...(by.get(x.date) ?? []), x]);
  return (
    <div className="text-[13px]">
      {c.deadlines.length > 0 && (
        <ul className="mb-2 space-y-0.5">
          {c.deadlines.map((d) => <li key={d.date + d.what}><span className="font-bold" style={{ color: "var(--accent)" }}>{md(d.date)}</span> <span style={{ color: "var(--text-secondary)" }}>{d.what}</span></li>)}
        </ul>
      )}
      {!c.earnings.length ? <p style={MUTED}>{month} 실적 발표 예정인 관심·후보·테마 기업이 없습니다.</p> : (
        <div className="grid gap-x-4 gap-y-1 sm:grid-cols-[3.5rem_1fr]">
          {[...by.entries()].map(([d, xs]) => (
            <div key={d} className="contents">
              <span className="font-bold" style={{ color: "var(--text-primary)", fontVariantNumeric: "tabular-nums" }}>{md(d)}</span>
              <span className="flex flex-wrap gap-x-2.5 gap-y-0.5">
                {xs.map((x) => (
                  <span key={`${x.market}:${x.symbol}`} className="whitespace-nowrap">
                    <StockLink market={x.market} symbol={x.symbol} style={{ color: x.tags.includes("내 관심") ? "var(--accent)" : "var(--text-secondary)" }}>{nameOf(x.market, x.symbol, x.name)}</StockLink>
                    <span className="ml-1 text-[11px]" style={FAINT}>{x.market === "KR" ? "한국" : "미국"}{x.estimate ? " · 날짜 미확정" : ""}</span>
                  </span>
                ))}
              </span>
            </div>
          ))}
        </div>
      )}
      <p className="mt-1.5 text-[12px]" style={FAINT}>
        내 워치리스트(주황) → 후보이면서 테마 소속 → 후보 → 테마 소속 순으로 최대 40곳{c.earnings_total > c.earnings.length ? ` (전체 ${c.earnings_total}곳)` : ""}. &apos;날짜 미확정&apos;은 회사가 발표일을 아직 확정하지 않아 바뀔 수 있는 것.
      </p>
    </div>
  );
}

function ReportView() {
  const params = useSearchParams();
  const router = useRouter();
  const want = params.get("month");
  const [data, setData] = useState<{ months: string[]; month?: string; report: Report | null } | null>(null);
  useEffect(() => {
    fetch(`/api/monthly-report${want ? `?month=${want}` : ""}`).then((r) => r.json()).then(setData).catch(() => setData({ months: [], report: null }));
  }, [want]);

  if (!data) return <p className="text-[13px]" style={MUTED}>불러오는 중…</p>;
  const r = data.report;
  if (!r) return <EmptyState title="아직 만든 월간 보고서가 없습니다" hint="매달 첫 월요일 아침에 지난달 보고서가 만들어집니다." />;
  const nextMonth = (() => { const [y, m] = r.month.split("-").map(Number); return monthKo(m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, "0")}`); })();

  return (
    <div className="mx-auto max-w-[980px] space-y-4">
      <PageHeader
        title={`월간 리서치 보고서 · ${monthKo(r.month)}`}
        desc={`${md(r.weeks[0])}~${md(r.weeks[r.weeks.length - 1])} 주까지 ${r.weeks.length}주 동안의 신호와 주간 브리핑 ${r.briefing_weeks.length}편을 한 달로 묶었습니다. 점수·등급·매수 의견은 넣지 않았습니다.`}
      >
        <div className="print-hidden mt-2 flex flex-wrap items-center gap-2 text-[12.5px]">
          {data.months.length > 1 && (
            <select value={r.month} onChange={(e) => router.push(`/report?month=${e.target.value}`)}
              className="rounded px-2 py-1" style={{ background: "var(--bg-inset)", border: "1px solid var(--border-ctrl)", color: "var(--text-primary)" }}>
              {data.months.map((m) => <option key={m} value={m}>{monthKo(m)}</option>)}
            </select>
          )}
          <button onClick={() => window.print()} className="rounded px-2.5 py-1" style={{ border: "1px solid var(--border-ctrl)", color: "var(--text-secondary)" }}>
            인쇄 · PDF로 저장
          </button>
          <span style={FAINT}>만든 시각 {r.generated_at}</span>
        </div>
      </PageHeader>

      <Section title="이달 요약" sub="아래 칸의 사실만으로 GPT가 쓴 글 · 숫자는 넣지 않음" tone="warm" className="print-avoid-break">
        {r.summary ? (
          <div className="space-y-2.5">
            {r.summary.split(/\n\s*\n/).map((p, i) => <p key={i} className="text-[14px] leading-relaxed" style={{ color: "var(--text-primary)" }}>{p}</p>)}
          </div>
        )
          : <p className="text-[13px]" style={MUTED}>이번 달은 요약을 만들지 못했습니다. 아래 칸을 보세요.</p>}
      </Section>

      <Section title="1. 시장 환경" sub="주별 조합 이름" className="print-avoid-break"><RegimeBlock r={r.regime} weeks={r.weeks} /></Section>
      <Section title="2. 테마 흐름" sub="세 축(뉴스·실적·주가) 라벨과 실적 축 변화"><ThemeFlow t={r.themes} weeks={r.weeks} /></Section>
      <Section title="3. 주시할 뉴스" sub="라벨이 붙은 테마별 · 주마다 한 건씩, 원문 제목 그대로"><NewsBlocks news={r.news} /></Section>
      <Section title="4. 테마별 기업 지도" sub="라벨이 붙었거나 실적 축이 바뀐 테마의 소속 기업 · 가치사슬 구간별"><CompanyMap maps={r.company_map} /></Section>
      <Section title="5. 워치리스트 한 달 변화">
        <div className="mb-3 grid gap-4 md:grid-cols-2">
          <ChangeBlock title="트랩 필터 통과 목록" c={r.watchlist.watchlist} />
          <ChangeBlock title="실적 반전 목록" c={r.watchlist.turnaround} />
        </div>
        {(r.month_events ?? []).length > 0 && (
          <div className="text-[13px]">
            <Sub>이달 공시·내부자 매수 등이 있었던 곳</Sub>
            <ul className="grid gap-x-4 gap-y-0.5 sm:grid-cols-2">
              {(r.month_events ?? []).map((x) => (
                <li key={`${x.market}:${x.symbol}`} className="flex flex-wrap items-baseline gap-x-1.5">
                  <StockLink market={x.market} symbol={x.symbol} style={{ color: "var(--text-primary)" }}>{nameOf(x.market, x.symbol, x.name)}</StockLink>
                  <span className="text-[11px]" style={FAINT}>{x.market === "KR" ? "한" : "미"}</span>
                  <span style={{ color: x.events.some((e) => e.startsWith("8-K") || e.startsWith("계약 해지")) ? "var(--orange)" : "var(--text-secondary)" }}>{x.events.join(" · ")}</span>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-[12px]" style={FAINT}>이달 주간 브리핑에 나온 내부자 매수(계획 매수 제외)·큰 공급계약·계약 해지·잠정실적 영업이익 전환·8-K 주의 공시·실적 반전 신규. 테마 지도 밖 종목 포함, 최대 40곳.</p>
          </div>
        )}
      </Section>
      <Section title="6. 관찰 노트 회고" sub="적어 둔 기대가 맞았는지" className="print-avoid-break"><Reviews rs={r.reviews} /></Section>
      <Section title={`7. ${nextMonth} 일정`} sub="실적 발표 · 공시 마감"><CalendarBlock c={r.calendar} month={nextMonth} /></Section>
    </div>
  );
}

export default function ReportPage() {
  return <Suspense fallback={null}><ReportView /></Suspense>;
}
