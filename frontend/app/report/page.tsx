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
// 내 검토 기록(2026-11-21, 사용자 요청) - scripts/generate_monthly_report.py decisions_section. 11월 보고서부터
interface DecRec { date: string; market: Mk; symbol: string; name: string; decision: string; checks: string; source: string; memo: string }
interface DecArrived { market: Mk; symbol: string; name: string; decision: string; decided_on: string; h: number; due: string;
                       ret: number; mkt: number | null; ex: number | null }
interface DecStat { h: number; decision: string; n: number; med: number | null; med_ex: number | null; beat: number; n_ex: number }
interface Decisions { total: number; recorded: DecRec[]; recorded_count: number; by_decision: Record<string, number>;
                      arrived: DecArrived[]; stats: DecStat[]; next: { date: string; h: number; n: number } | null }
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
  decisions?: Decisions | null;
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
function Sub({ children }: { children: ReactNode }) {
  return <h3 className="h-sub mb-2 mt-4 first:mt-0">{children}</h3>;
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
                        <span style={{ color: "var(--text-primary)" }}>{x.combos.join(" · ")}</span>
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
                    {weeks.map((w) => <td key={w} className="py-1.5 pr-3">{by.get(w) ? <span className="whitespace-nowrap" style={{ color: "var(--text-primary)" }}>{by.get(w)!.label_ko || by.get(w)!.label}</span> : <span style={FAINT}>-</span>}</td>)}
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

// 기업 지도(2026-11-15 가독성) - 7개 테마 전부 펼치면 화면 3분의 1이라 테마마다 요약 한 줄(기업 수·이달 일 있었던 곳·빈 구간)만 두고 접는다.
// 인쇄할 때는 전부 펼친다(globals.css .print-expand).
function CompanyMap({ maps }: { maps: MapTheme[] }) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  if (!maps.length) return <p className="text-[13px]" style={MUTED}>이달 지도로 그릴 테마가 없습니다.</p>;
  const toggle = (k: string) => setOpen((o) => { const n = new Set(o); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  return (
    <div>
      {maps.map((t) => {
        const k = `${t.market}:${t.theme_id}`;
        const all = t.groups.flatMap((g) => g.items);
        const ev = all.filter((it) => it.events.length);
        const gaps = t.groups.filter((g) => g.n && !g.items.length).map((g) => g.label.split(/[(:]/)[0].trim());
        const on = open.has(k);
        return (
        <div key={k} className="print-avoid-break py-2" style={{ borderTop: "1px solid var(--border-dim)" }}>
          <button type="button" onClick={() => toggle(k)} aria-expanded={on} className="flex w-full flex-wrap items-baseline gap-x-2 gap-y-0.5 text-left hover:brightness-125">
            <span className="text-[14px] font-bold" style={{ color: "var(--text-primary)" }}>{t.theme}</span>
            <MkTag m={t.market} />
            <span className="text-[12.5px]" style={{ color: "var(--text-secondary)" }}>
              {all.length}곳{ev.length ? ` · 이달 일 있었던 곳 ${ev.length}` : ""}{gaps.length ? ` · 빈 구간: ${gaps.join(", ")}` : ""}
            </span>
            <span className="print-hidden ml-auto text-[12px]" style={FAINT}>{on ? "접기 ▴" : "펼치기 ▾"}</span>
          </button>
          <div hidden={!on} className="print-expand mt-2 space-y-1.5">
            <a href={`/radar/theme?id=${encodeURIComponent(t.theme_id)}&market=${t.market}`} className="print-hidden inline-block text-[12px] hover:underline" style={{ color: "var(--accent)" }}>테마 화면으로 →</a>
            {t.groups.map((g) => (
              <div key={g.n} className="flex flex-col gap-1 sm:flex-row sm:gap-3">
                <div className="shrink-0 text-[12.5px] sm:w-56" style={g.n ? { color: "var(--text-secondary)" } : FAINT}>
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
        );
      })}
      <p className="mt-2 text-[12px]" style={FAINT}>
        구간은 가치사슬 순서(앞 → 뒤). 점 색은 월말 기준 실적 판정(초록 테마 중앙값보다 좋음 · 회색 못 미침 · 흐림 데이터 부족). &apos;일부&apos;는 사업 일부만 이 테마에 해당하는 기업. 테두리가 밝은 기업은 이달 공시·내부자 매수 같은 일이 있었던 곳.
      </p>
    </div>
  );
}

// 한 달 새로 든 곳이 수십 곳이면 칸이 길어진다(10월 29곳) - 이름은 12곳까지, 나머지는 외 N곳(2026-11-15)
const NAMES_MAX = 12;
function ChangeBlock({ title, c }: { title: string; c: Change | null }) {
  if (!c) return <div className="text-[13px]"><Sub>{title}</Sub><p style={MUTED}>비교할 두 주가 없습니다.</p></div>;
  const names = (xs: Ref[], n: number) => (
    <span className="flex flex-wrap gap-x-2 gap-y-0.5">
      {xs.slice(0, NAMES_MAX).map((x) => <StockLink key={`${x.market}:${x.symbol}`} market={x.market} symbol={x.symbol} style={{ color: "var(--text-secondary)" }}>{nameOf(x.market, x.symbol, x.name)}</StockLink>)}
      {n > Math.min(xs.length, NAMES_MAX) && <span style={FAINT}>{xs.length ? `외 ${n - Math.min(xs.length, NAMES_MAX)}곳` : `${n}곳(이름 목록 없음)`}</span>}
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

const DEC_KO: Record<string, string> = { watch: "관심", hold: "보류", pass: "제외" };
const DEC_COLOR: Record<string, string> = { watch: "var(--accent)", hold: "var(--text-secondary)", pass: "var(--text-muted)" };
const H_KO: Record<number, string> = { 28: "4주", 84: "12주", 182: "26주" };
const pct = (v: number | null) => (v == null ? "-" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`);
const pp = (v: number | null) => (v == null ? "-" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%p`);
const tone = (v: number | null) => (v == null ? "var(--text-faint)" : v >= 0 ? "var(--good)" : "var(--danger)");

function DecisionBlock({ d }: { d: Decisions | null | undefined }) {
  if (!d) return <p className="text-[13px]" style={MUTED}>아직 남긴 검토 기록이 없습니다. 기업 카드의 &lsquo;검토 기록&rsquo; 칸에서 관심·보류·제외를 남기면 4·12·26주 뒤 결과가 여기 모입니다.</p>;
  return (
    <div className="space-y-4 text-[13px]">
      <div>
        <Sub>이달 남긴 기록 {d.recorded_count}건{d.recorded_count ? ` (${["watch", "hold", "pass"].filter((k) => d.by_decision[k]).map((k) => `${DEC_KO[k]} ${d.by_decision[k]}`).join(" · ")})` : ""}</Sub>
        {d.recorded.length ? (
          <ul className="space-y-1">
            {d.recorded.map((x, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-x-2">
                <span style={FAINT}>{md(x.date)}</span>
                <b style={{ color: DEC_COLOR[x.decision] }}>{DEC_KO[x.decision] ?? x.decision}</b>
                <StockLink market={x.market} symbol={x.symbol} style={{ color: "var(--text-primary)", fontWeight: 700 }}>{nameOf(x.market, x.symbol, x.name)}</StockLink>
                <MkTag m={x.market} />
                {x.checks && <span style={MUTED}>{x.checks}</span>}
                <span style={FAINT}>· {x.source}</span>
                {x.memo && <span style={{ color: "var(--text-secondary)" }}>&ldquo;{x.memo}&rdquo;</span>}
              </li>
            ))}
          </ul>
        ) : <p style={FAINT}>이달 새로 남긴 기록 없음</p>}
      </div>
      <div>
        <Sub>이달 도착한 결과 {d.arrived.length}건</Sub>
        {d.stats.length ? (
          <>
            <ul className="mb-2 space-y-0.5">
              {d.stats.map((s) => (
                <li key={`${s.h}${s.decision}`} style={{ fontVariantNumeric: "tabular-nums" }}>
                  <span style={MUTED}>{H_KO[s.h]} 뒤</span> <b style={{ color: DEC_COLOR[s.decision] }}>{DEC_KO[s.decision]}</b> {s.n}건 · 중앙값 <b style={{ color: tone(s.med) }}>{pct(s.med)}</b>
                  {s.n_ex > 0 && <span style={MUTED}> · 시장 대비 <b style={{ color: tone(s.med_ex) }}>{pp(s.med_ex)}</b> · {s.n_ex}건 중 {s.beat}건 앞섬</span>}
                </li>
              ))}
            </ul>
            <ul className="space-y-0.5 text-[12.5px]">
              {d.arrived.map((x, i) => (
                <li key={i} className="flex flex-wrap items-baseline gap-x-2" style={{ fontVariantNumeric: "tabular-nums" }}>
                  <span style={FAINT}>{md(x.decided_on)} {DEC_KO[x.decision]} → {H_KO[x.h]} 뒤</span>
                  <StockLink market={x.market} symbol={x.symbol} style={{ color: "var(--text-primary)" }}>{nameOf(x.market, x.symbol, x.name)}</StockLink>
                  <span style={{ color: tone(x.ret) }}>{pct(x.ret)}</span>
                  <span style={MUTED}>시장 {pct(x.mkt)} · 차이 <span style={{ color: tone(x.ex) }}>{pp(x.ex)}</span></span>
                </li>
              ))}
            </ul>
          </>
        ) : <p style={FAINT}>이달 끝 날짜가 온 결과 없음{d.next ? ` · 다음 결과 ${md(d.next.date)} (${H_KO[d.next.h]} ${d.next.n}건)` : ""}</p>}
      </div>
      <p className="text-[12px]" style={FAINT}>
        시작가는 기록한 다음 거래일 종가, 시장은 미국 SPY·한국 KODEX 200. 관심·보류·제외 모두 같은 방식으로 잽니다(제외한 게 맞았는지도 보려고). 분포만 - 점수·적중률 아님 · 전체는 성적표 화면.
      </p>
    </div>
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
                    {x.estimate && <span className="ml-0.5 text-[11px]" style={FAINT}>(미정)</span>}
                  </span>
                ))}
              </span>
            </div>
          ))}
        </div>
      )}
      <p className="mt-1.5 text-[12px]" style={FAINT}>
        내 워치리스트(주황) → 후보이면서 테마 소속 → 후보 → 테마 소속 순으로 최대 40곳{c.earnings_total > c.earnings.length ? ` (전체 ${c.earnings_total}곳)` : ""}. &apos;(미정)&apos;은 회사가 발표일을 아직 확정하지 않아 바뀔 수 있는 것. 한글 이름은 한국, 영문은 미국 종목.
      </p>
    </div>
  );
}

// 이달 공시 등(2026-11-15 가독성) - 예전엔 종목마다 한 줄(40줄)이라 같은 사유가 줄마다 반복됐다. 사유별 한 줄로 묶는다.
// 순서는 경고 → 계약 → 내부자 → 잠정실적 → 실적 반전(scripts/generate_monthly_report.py EVENT_ORDER와 같은 취지), 이름 순서는 보고서 그대로.
const EVENT_GROUPS: { key: string; label: string; match: (e: string) => boolean; warn?: boolean }[] = [
  { key: "term", label: "⚠ 계약 해지", match: (e) => e.startsWith("계약 해지"), warn: true },
  { key: "8k", label: "⚠ 8-K 주의", match: (e) => e.startsWith("8-K"), warn: true },
  { key: "contract", label: "큰 공급계약", match: (e) => e.startsWith("큰 공급계약") },
  { key: "insider", label: "내부자 매수", match: (e) => e.startsWith("내부자") },
  { key: "prelim", label: "잠정실적 전환", match: (e) => e.startsWith("잠정실적") },
  { key: "turn", label: "실적 반전 신규", match: (e) => e.startsWith("실적 반전") },
];
function EventGroups({ evs }: { evs: NonNullable<Report["month_events"]> }) {
  const rows = [...EVENT_GROUPS, { key: "etc", label: "기타", match: (e: string) => !EVENT_GROUPS.some((g) => g.match(e)) }]
    .map((g) => ({ ...g, xs: evs.flatMap((x) => x.events.filter(g.match).slice(0, 1).map((e) => ({ ...x, e }))) }))
    .filter((g) => g.xs.length);
  return (
    <div>
      {rows.map((g) => (
        <div key={g.key} className="flex flex-col gap-0.5 py-1.5 sm:flex-row sm:gap-3" style={{ borderTop: "1px solid var(--border-dim)" }}>
          <span className="shrink-0 sm:w-40" style={{ color: "warn" in g && g.warn ? "var(--danger)" : "var(--text-muted)" }}>{g.label} {g.xs.length}</span>
          <span className="min-w-0 flex-1 leading-relaxed">
            {g.xs.map((x, i) => (
              <span key={`${x.market}:${x.symbol}`}>
                {i > 0 && <span style={FAINT}> · </span>}
                <StockLink market={x.market} symbol={x.symbol} style={{ color: "var(--text-primary)" }}>{nameOf(x.market, x.symbol, x.name)}</StockLink>
                {g.key === "prelim" && <span className="text-[11.5px]" style={MUTED}> {x.e.replace("잠정실적 영업이익 ", "")}</span>}
                {g.key === "insider" && x.e.includes("여러 명") && <span className="text-[11.5px]" style={MUTED}> 여러 명</span>}
              </span>
            ))}
          </span>
        </div>
      ))}
    </div>
  );
}

// 한 달 한눈에(2026-11-15 가독성) - 아래 칸 값을 코드가 한 줄씩 옮긴 것. GPT를 거치지 않는다(원칙 2), 점수 없음(원칙 1).
const ARROW_SHORT: Record<string, string> = { up2: "크게 오름", up1: "오름", flat: "보합", down: "내림", na: "판단 불가" };
function runs(xs: string[]): string {
  const out: string[] = [];
  for (const x of xs) if (out[out.length - 1] !== x) out.push(x);
  return out.join(" → ");
}
function MonthGlance({ r }: { r: Report }) {
  const row = (label: string, href: string, body: ReactNode) => (
    <div className="flex flex-col gap-0.5 py-1.5 text-[13.5px] sm:flex-row sm:gap-3" style={{ borderTop: "1px solid var(--border-dim)" }}>
      <a href={href} className="shrink-0 font-semibold hover:underline sm:w-24" style={{ color: "var(--text-muted)" }}>{label}</a>
      <div className="min-w-0 flex-1 leading-relaxed" style={{ color: "var(--text-secondary)" }}>{body}</div>
    </div>
  );
  const sep = <span style={FAINT}> · </span>;
  const join = (xs: ReactNode[]) => xs.map((x, i) => <span key={i}>{i > 0 && sep}{x}</span>);
  const mks = (["US", "KR"] as Mk[]).filter((m) => (r.regime[m] ?? []).length);
  // 라벨 테마 - 마지막으로 붙은 라벨 기준으로 시장·라벨별로 묶는다
  const lab = new Map<string, { m: Mk; label: string; names: string[] }>();
  for (const t of r.themes.labeled) {
    const last = (t.labels ?? []).slice().sort((a, b) => a.week.localeCompare(b.week)).pop();
    if (!last) continue;
    const k = `${t.market}:${last.label}`;
    const cur = lab.get(k) ?? { m: t.market, label: last.label_ko || last.label, names: [] };
    cur.names.push(t.theme); lab.set(k, cur);
  }
  const hits = r.reviews.flatMap((x) => x.results);
  const ok = hits.filter((x) => x.hit === true).length, miss = hits.filter((x) => x.hit === false).length, na = hits.filter((x) => x.hit == null).length;
  const mine = r.calendar.earnings.filter((x) => x.tags.includes("내 관심"));
  const chg = (c: Change | null, name: string) => c && `${name} ${c.end_total}곳 (+${c.added_count} −${c.removed_count})`;
  const wl = [chg(r.watchlist.watchlist, "재무 필터 통과"), chg(r.watchlist.turnaround, "실적 반전")].filter(Boolean) as string[];
  return (
    <Section title="한 달 한눈에" sub="아래 칸 값을 한 줄씩 옮긴 것 · 점수·추천 아님" className="print-avoid-break">
      {mks.length > 0 && row("시장 환경", "#s1", join(mks.map((m) => (
        <><FlagIcon market={m} size={12} /> {runs((r.regime[m] ?? []).map((x) => x.combos.length ? x.combos.join("·") : "뚜렷한 조합 없음"))}</>
      ))))}
      {row("라벨 테마", "#s2", lab.size ? join([...lab.values()].map((x) => (
        <><FlagIcon market={x.m} size={12} /> <b style={{ color: "var(--text-primary)" }}>{x.names.join("·")}</b> <span style={MUTED}>{x.label}</span></>
      ))) : <span style={FAINT}>없음</span>)}
      {r.themes.earn_turns.length > 0 && row("실적 축 변화", "#s2", join(r.themes.earn_turns.map((t) => (
        <><FlagIcon market={t.market} size={12} /> <b style={{ color: "var(--text-primary)" }}>{t.theme}</b> <span style={MUTED}>{ARROW_SHORT[t.from ?? "na"]} → </span><Arrow a={t.to} /></>
      ))))}
      {wl.length > 0 && row("워치리스트", "#s5", join(wl))}
      {row("회고", "#s6", hits.length ? <>맞음 <b style={{ color: "var(--text-primary)" }}>{ok}</b>{sep}빗나감 <b style={{ color: "var(--text-primary)" }}>{miss}</b>{na ? <>{sep}판단 불가 {na}</> : null}</>
        : <span style={FAINT}>{r.reviews.length ? "적어 둔 기대가 있는 노트 없음" : "회고 시점이 온 노트 없음"}</span>)}
      {r.decisions && row("검토 기록", "#s8", <>이달 {r.decisions.recorded_count}건{sep}결과 도착 {r.decisions.arrived.length}건{r.decisions.stats.filter((s) => s.n_ex > 0).length ? <>{sep}{r.decisions.stats.filter((s) => s.n_ex > 0).map((s) => `${H_KO[s.h]} ${DEC_KO[s.decision]} 시장 대비 ${pp(s.med_ex)}`).join(", ")}</> : null}</>)}
      {row("다음 달", "#s7", (r.calendar.deadlines.length || mine.length) ? join([
        ...r.calendar.deadlines.map((d) => <>{md(d.date)} {d.what}</>),
        ...(mine.length ? [<>내 관심 실적 발표 {mine.map((x, i) => (
          <span key={x.symbol}>{i > 0 && ", "}<StockLink market={x.market} symbol={x.symbol} style={{ color: "var(--text-primary)" }}>{nameOf(x.market, x.symbol, x.name)}</StockLink> {md(x.date)}</span>
        ))}</>] : []),
      ]) : <span style={FAINT}>표시할 일정 없음</span>)}
    </Section>
  );
}

// 이달 요약 문단 제목(2026-11-15 가독성) - GPT가 문단을 나누는 방식이 달마다 달라 순서로 붙이지 않고 문단에 나온 말로 고른다. 글은 그대로.
function paraLabel(p: string): string {
  const first = p.split(/(?<=다\.)\s/)[0];
  const t: string[] = [];
  if (/시장은|시장 환경/.test(first)) t.push("시장");
  if (p.includes("한국에서는")) t.push("한국 테마");
  if (p.includes("미국에서는")) t.push("미국 테마");
  if (!t.some((x) => x.endsWith("테마")) && /테마별로는/.test(p)) t.push("테마");
  if (p.includes("기업 지도")) t.push("기업 지도");
  if (p.includes("워치리스트")) t.push("워치리스트");
  if (p.includes("관찰 노트")) t.push("회고");
  if (p.includes("다음 달")) t.push("다음 달");
  return t.join(" · ");
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
    <div className="mx-auto max-w-[980px] space-y-6">
      <PageHeader
        title={`월간 리서치 보고서 · ${monthKo(r.month)}`} intro="report"
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

      <MonthGlance r={r} />

      <Section title="이달 요약" sub="아래 칸의 사실만으로 GPT가 쓴 글 · 숫자는 넣지 않음" tone="warm" className="print-avoid-break">
        {r.summary ? (
          <div className="space-y-3">
            {r.summary.split(/\n\s*\n/).map((p, i) => {
              const lb = paraLabel(p);
              return (
                <div key={i}>
                  {lb && <p className="mb-0.5 text-[12.5px] font-bold" style={{ color: "var(--accent)" }}>{lb}</p>}
                  <p className="t-lead">{p}</p>
                </div>
              );
            })}
          </div>
        )
          : <p className="text-[13px]" style={MUTED}>이번 달은 요약을 만들지 못했습니다. 아래 칸을 보세요.</p>}
      </Section>

      <Section id="s1" title="1. 시장 환경" sub="주별 조합 이름" className="print-avoid-break"><RegimeBlock r={r.regime} weeks={r.weeks} /></Section>
      <Section id="s2" title="2. 테마 흐름" sub="세 축(뉴스·실적·주가) 라벨과 실적 축 변화"><ThemeFlow t={r.themes} weeks={r.weeks} /></Section>
      <Section id="s3" title="3. 주시할 뉴스" sub="라벨이 붙은 테마별 · 주마다 한 건씩, 원문 제목 그대로"><NewsBlocks news={r.news} /></Section>
      <Section id="s4" title="4. 테마별 기업 지도" sub="라벨이 붙었거나 실적 축이 바뀐 테마의 소속 기업 · 가치사슬 구간별 · 테마를 누르면 펼침"><CompanyMap maps={r.company_map} /></Section>
      <Section id="s5" title="5. 워치리스트 한 달 변화">
        <div className="mb-3 grid gap-4 md:grid-cols-2">
          <ChangeBlock title="트랩 필터 통과 목록" c={r.watchlist.watchlist} />
          <ChangeBlock title="실적 반전 목록" c={r.watchlist.turnaround} />
        </div>
        {(r.month_events ?? []).length > 0 && (
          <div className="text-[13px]">
            <Sub>이달 공시·내부자 매수 등이 있었던 곳</Sub>
            <EventGroups evs={r.month_events ?? []} />
            <p className="mt-1 text-[12px]" style={FAINT}>이달 주간 브리핑에 나온 내부자 매수(계획 매수 제외)·큰 공급계약·계약 해지·잠정실적 영업이익 전환·8-K 주의 공시·실적 반전 신규. 테마 지도 밖 종목 포함, 최대 40곳.</p>
          </div>
        )}
      </Section>
      <Section id="s6" title="6. 관찰 노트 회고" sub="적어 둔 기대가 맞았는지" className="print-avoid-break"><Reviews rs={r.reviews} /></Section>
      <Section id="s8" title="7. 내 검토 기록" sub="이달 남긴 관심·보류·제외와 이달 도착한 4·12·26주 결과" className="print-avoid-break"><DecisionBlock d={r.decisions} /></Section>
      <Section id="s7" title={`8. ${nextMonth} 일정`} sub="실적 발표 · 공시 마감"><CalendarBlock c={r.calendar} month={nextMonth} /></Section>
    </div>
  );
}

export default function ReportPage() {
  return <Suspense fallback={null}><ReportView /></Suspense>;
}
