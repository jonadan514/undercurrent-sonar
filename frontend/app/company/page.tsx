"use client";

// 기업 기초조사 카드(2026-11-05, 마스터 플랜 2단계 첫 항목) - /company?stock=US:MU
// 리서치 실행 가이드 2단계(기업 하나를 보는 순서)를 그대로 따라간다: 무엇을 하는 회사인가 → 숫자 확인 → 최근 일 → 주의할 사실 → 내 기록.
// 워치리스트 후보가 아니어도 열린다. 종합 점수·매수 판단 없음(원칙 1), 숫자는 저장된 값 그대로(원칙 2), 없으면 "데이터 부족"(원칙 4).

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import PageHeader from "@/src/components/PageHeader";
import { Section } from "@/src/components/Section";
import EmptyState from "@/src/components/EmptyState";
import { externalQuoteUrl } from "@/src/components/StockLink";
import { ObservationForm } from "@/src/components/Observation";
import { themeName } from "@/src/lib/themeNames";
import { labelWithKo } from "@/src/lib/labelNames";
import { tierLabel } from "@/src/lib/valuation";
import { ChecklistSection, InsiderSection, InstitutionSection, NarrativeSection, ThemePeerSection, Us8kSection } from "@/src/components/stock/StockSections";

type Theme = { theme_id: string; linkage: string; stage: string | null; evidence: string | null; label: string | null;
               news: string | null; earn: string | null; price: string | null; week: string | null };
type Quarter = { quarter: string; revenue: number | null; operating_income: number | null; net_income: number | null; source: string };
type Company = {
  market: "US" | "KR"; symbol: string; name: string | null;
  profile: { sector: string | null; industry: string | null; summary: string | null } | null;
  themes: Theme[];
  screening: { status: string; reasons: string[]; piotroski: number | null; roe: number | null; screened_at: string } | null;
  candidate: Record<string, string | number | null> | null;
  quarters: Quarter[];
  kr_disclosures: { rcept_no: string; date: string; kind: string; title: string | null; pct: number | null }[];
  next_earnings: { date: string; date_end: string; estimate: boolean } | null;
  sentiment: { now: string | null; prev: string | null } | null;
  mine: { note: string | null; added_at: string } | null;
  notes: { id: number; created_at: string; hypothesis: string }[];
  cautions: { text: string; why: string }[];
};

const GOOD = "#4ade80", BAD = "#f87171", WARN = "#facc15", INFO = "#6fb3b8", ACCENT = "#ffb020";
const MUTED = "var(--text-muted)", FAINT = "var(--text-faint)", SECONDARY = "var(--text-secondary)";
const LINKAGE: Record<string, { ko: string; color: string }> = {
  direct: { ko: "주력", color: GOOD }, partial: { ko: "일부", color: INFO }, peripheral: { ko: "간접", color: "#8b8271" },
};
const DISC_KO: Record<string, string> = { contract: "공급계약", termination: "계약 해지", prelim: "잠정실적", notice: "실적 발표 예정", amend: "정정" };

function arrow(a: string | null): { g: string; c: string } {
  if (a === "up2") return { g: "↑↑", c: GOOD };
  if (a === "up1") return { g: "↑", c: GOOD };
  if (a === "down") return { g: "↓", c: BAD };
  if (a === "flat") return { g: "→", c: "#8b8271" };
  return { g: "–", c: "#5a5446" };
}
function money(v: number | null, market: string): string {
  if (v == null) return "-";
  const a = Math.abs(v), s = v < 0 ? "-" : "";
  if (market === "KR") return a >= 1e12 ? `${s}${(a / 1e12).toFixed(2)}조` : `${s}${Math.round(a / 1e8).toLocaleString()}억`;
  return a >= 1e9 ? `${s}$${(a / 1e9).toFixed(2)}B` : `${s}$${(a / 1e6).toFixed(0)}M`;
}
const pct = (v: number | null | undefined, d = 1) => (v == null ? "-" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(d)}%`);
const md = (s: string) => s.slice(5).replace("-", "/");

function Step({ n }: { n: string; children?: React.ReactNode }) {
  return <span className="text-[11px] font-bold px-1.5 py-0.5 rounded mr-1.5" style={{ background: "#ffb02022", color: ACCENT }}>{n}</span>;
}

function QuarterTable({ quarters, market }: { quarters: Quarter[]; market: string }) {
  if (!quarters.length) return <p className="text-[12.5px]" style={{ color: MUTED }}>분기 재무 데이터 부족 - 공시 원본 표에 이 종목 분기가 아직 없습니다.</p>;
  const byQ = new Map(quarters.map((q) => [q.quarter, q]));
  const ago = (q: string) => byQ.get(`${Number(q.slice(0, 4)) - 1}${q.slice(4)}`);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12.5px]" style={{ fontVariantNumeric: "tabular-nums" }}>
        <thead>
          <tr style={{ color: MUTED }}>
            {["분기", "매출", "1년 전 대비", "영업이익", "영업이익률", "순이익", "출처"].map((h) => (
              <th key={h} className="text-right first:text-left font-normal px-2 py-1 whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {quarters.map((q) => {
            const a = ago(q.quarter);
            const yoy = q.revenue != null && a?.revenue ? q.revenue / a.revenue - 1 : null;
            const om = q.revenue && q.revenue > 0 && q.operating_income != null ? q.operating_income / q.revenue : null;
            return (
              <tr key={q.quarter} style={{ borderTop: "1px solid var(--border)" }}>
                <td className="px-2 py-1 whitespace-nowrap" style={{ color: SECONDARY }}>{q.quarter}</td>
                <td className="px-2 py-1 text-right">{money(q.revenue, market)}</td>
                <td className="px-2 py-1 text-right" style={{ color: yoy == null ? FAINT : yoy >= 0 ? GOOD : BAD }}>{pct(yoy)}</td>
                <td className="px-2 py-1 text-right" style={{ color: q.operating_income != null && q.operating_income < 0 ? BAD : undefined }}>{money(q.operating_income, market)}</td>
                <td className="px-2 py-1 text-right">{om == null ? "-" : `${(om * 100).toFixed(1)}%`}</td>
                <td className="px-2 py-1 text-right" style={{ color: q.net_income != null && q.net_income < 0 ? BAD : undefined }}>{money(q.net_income, market)}</td>
                <td className="px-2 py-1 text-right text-[11px]" style={{ color: FAINT }}>{q.source}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-1.5 text-[11px]" style={{ color: FAINT }}>공시 원본(DART·SEC)을 먼저, 없으면 yfinance. 분기는 분기 말일의 달력 분기 - 회계연도가 다른 회사는 회사 표기와 다를 수 있습니다.</p>
    </div>
  );
}

function CompanyView() {
  const stock = useSearchParams().get("stock") ?? "";
  const [d, setD] = useState<Company | null | undefined>(undefined);
  const [obsOpen, setObsOpen] = useState(false);
  useEffect(() => {
    if (!stock) { setD(null); return; }
    let cancel = false;
    fetch(`/api/company?stock=${encodeURIComponent(stock)}`).then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (!cancel) setD(j && !j.error ? j : null); }).catch(() => { if (!cancel) setD(null); });
    return () => { cancel = true; };
  }, [stock]);

  if (d === undefined) return <p className="text-[13px] p-6" style={{ color: MUTED }}>불러오는 중...</p>;
  if (d === null) return <EmptyState title="종목을 찾지 못했습니다" hint="주소는 /company?stock=US:MU 또는 /company?stock=KR:005930 형식입니다." />;

  const c = { market: d.market, symbol: d.symbol };
  const sc = d.screening;
  const scText = !sc ? "판정 없음 - 재무 필터 스크리닝 대상 밖이거나 아직 안 돌았습니다"
    : sc.status === "pass" ? `통과${sc.piotroski != null ? ` · F-Score ${sc.piotroski}` : ""}`
    : sc.status === "fail" ? `탈락 · ${sc.reasons.slice(0, 3).join(" · ") || "사유 미기록"}`
    : "데이터 부족 - 계산 못 한 항목이 있음(탈락 아님)";
  const scColor = !sc ? MUTED : sc.status === "pass" ? GOOD : sc.status === "fail" ? BAD : WARN;
  const cand = d.candidate;

  return (
    <div className="space-y-4 max-w-5xl">
      <PageHeader title={`${d.name ?? d.symbol}`} prefix={<span className="text-[12px] mr-2" style={{ color: MUTED }}>{d.market === "KR" ? "🇰🇷" : "🇺🇸"} {d.symbol}</span>}
        desc={[d.profile?.sector, d.profile?.industry].filter(Boolean).join(" · ") || "기업 기초조사 카드"}>
        <div className="flex flex-wrap gap-2 text-[12px] mt-1">
          {d.mine && <span className="px-2 py-0.5 rounded" style={{ background: "#ffb02022", color: ACCENT }}>⭐ 내 워치리스트</span>}
          {cand && <Link href={`/watchlist?stock=${encodeURIComponent(`${d.market}:${d.symbol}`)}`} className="px-2 py-0.5 rounded underline" style={{ color: GOOD }}>이번 주 워치리스트 후보</Link>}
          {d.next_earnings && <span className="px-2 py-0.5 rounded" style={{ border: "1px solid var(--border)", color: SECONDARY }}>
            실적 발표 {md(d.next_earnings.date)}{d.next_earnings.estimate ? "(예상)" : ""}</span>}
          <a href={externalQuoteUrl(d.market, d.symbol)} target="_blank" rel="noopener noreferrer" className="underline" style={{ color: MUTED }}>외부 시세 ↗</a>
        </div>
      </PageHeader>

      <p className="text-[12px]" style={{ color: FAINT }}>
        리서치 실행 가이드 2단계 순서대로 모았습니다. 점수나 매수 판단은 없습니다 - 판단은 직접 하고 아래 &quot;내 기록&quot;에 남기세요.
      </p>

      {/* ① 무엇을 하는 회사인가 */}
      <Section title={<><Step n="2-1·2-2">{null}</Step>무엇을 하는 회사인가</>} sub="사업 요약 원문(yfinance, 영문) · 소속 테마와 근거">
        {d.profile?.summary
          ? <p className="text-[12.5px] leading-relaxed" style={{ color: SECONDARY }}>{d.profile.summary}</p>
          : <p className="text-[12.5px]" style={{ color: MUTED }}>사업 요약 데이터 부족</p>}
        <div className="mt-3 space-y-1.5">
          {d.themes.length === 0 && <p className="text-[12.5px]" style={{ color: MUTED }}>승인된 소속 테마 없음</p>}
          {d.themes.map((t) => {
            const lk = LINKAGE[t.linkage] ?? LINKAGE.direct;
            return (
              <div key={t.theme_id} className="rounded-lg p-2.5" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                <div className="flex flex-wrap items-center gap-2">
                  <Link href={`/radar/theme?id=${t.theme_id}&market=${d.market}`} className="text-[13px] font-bold hover:underline" style={{ color: "var(--text-primary)" }}>
                    {themeName(t.theme_id).ko}</Link>
                  <span className="text-[11px] px-1.5 rounded" style={{ color: lk.color, border: `1px solid ${lk.color}55` }}>{lk.ko}</span>
                  {t.stage && <span className="text-[11.5px]" style={{ color: MUTED }}>{t.stage}</span>}
                  <span className="ml-auto text-[12px] whitespace-nowrap" style={{ fontFamily: "var(--font-mono, monospace)" }}>
                    {([["뉴스", t.news], ["실적", t.earn], ["주가", t.price]] as const).map(([k, a]) => {
                      const ar = arrow(a); return <span key={k} className="ml-2"><span style={{ color: FAINT }}>{k}</span> <b style={{ color: ar.c }}>{ar.g}</b></span>;
                    })}
                  </span>
                  {t.label && <span className="text-[11.5px] font-bold" style={{ color: ACCENT }}>{labelWithKo(t.label)}</span>}
                </div>
                {t.evidence && <p className="mt-1 text-[12px] leading-relaxed" style={{ color: MUTED }}>근거: {t.evidence}</p>}
              </div>
            );
          })}
          {d.themes.some((t) => t.linkage === "peripheral") && (
            <p className="text-[11px]" style={{ color: FAINT }}>간접(peripheral)은 테마 신호 계산에 넣지 않습니다 - 테마가 좋아도 이 회사 실적과는 거리가 있을 수 있습니다.</p>
          )}
        </div>
      </Section>

      {/* ② 숫자 확인 */}
      <Section title={<><Step n="2-3">{null}</Step>숫자 확인</>} sub="재무 필터 판정 · 최근 8분기 · 같은 테마 동료 대비">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[12.5px]">
          <div className="rounded-lg p-2.5" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
            <p style={{ color: MUTED }}>재무 필터</p>
            <p className="font-semibold" style={{ color: scColor }}>{scText}</p>
            {sc?.screened_at && <p className="text-[11px]" style={{ color: FAINT }}>{sc.screened_at.slice(0, 10)} 기준</p>}
          </div>
          <div className="rounded-lg p-2.5" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
            <p style={{ color: MUTED }}>밸류 · 성장 (워치리스트 후보일 때만)</p>
            {cand ? (
              <p style={{ color: SECONDARY }}>
                밸류 <b>{tierLabel(cand.valuation_tier as string | null)}</b> · PSR {cand.psr != null ? Number(cand.psr).toFixed(2) : "-"} · PER {cand.per != null ? Number(cand.per).toFixed(1) : "-"}
                <br />성장 <b>{(cand.growth_tier as string) ?? "-"}</b> · 매출 3년 {pct(cand.revenue_cagr_3y as number | null)} · 최근 1년 {pct(cand.revenue_yoy as number | null)}
                {cand.fcf_yield_3y != null && <> · FCF 수익률 3년 {pct(cand.fcf_yield_3y as number, 1)}</>}
              </p>
            ) : <p style={{ color: MUTED }}>후보가 아니라 계산하지 않음</p>}
          </div>
        </div>
        <div className="mt-3"><QuarterTable quarters={d.quarters} market={d.market} /></div>
        <div className="mt-3"><ThemePeerSection c={c} /></div>
      </Section>

      {/* ③ 최근 일 */}
      <Section title={<><Step n="2-4">{null}</Step>최근 일</>} sub="공시 · 8-K · 내부자 매수 · 13F · 관심도">
        {d.market === "KR" && (
          d.kr_disclosures.length ? (
            <div className="mb-3 space-y-0.5 text-[12.5px]">
              {d.kr_disclosures.map((x) => (
                <div key={x.rcept_no} className="flex gap-2 min-w-0">
                  <span className="shrink-0 w-11" style={{ color: FAINT }}>{md(x.date)}</span>
                  <span className="shrink-0" style={{ color: x.kind === "termination" ? BAD : INFO }}>{DISC_KO[x.kind] ?? x.kind}</span>
                  <a href={`https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${x.rcept_no}`} target="_blank" rel="noopener noreferrer" className="truncate hover:underline" style={{ color: SECONDARY }}>
                    {x.title ?? "공시"}{x.pct != null ? ` (매출 대비 ${x.pct.toFixed(1)}%)` : ""}</a>
                </div>
              ))}
            </div>
          ) : <p className="mb-3 text-[12.5px]" style={{ color: MUTED }}>최근 120일 한국 공시(공급계약·해지·잠정실적 등) 없음</p>
        )}
        <div className="space-y-2">
          {d.market === "US" && <Us8kSection c={c} />}
          <InsiderSection c={c} />
          {d.market === "US" && <InstitutionSection c={c} />}
          <NarrativeSection c={c} />
        </div>
      </Section>

      {/* ④ 주의할 사실 */}
      <Section title={<><Step n="2-5·2-6">{null}</Step>주의할 사실</>} sub="데이터에서 코드가 뽑은 것 - 판정이 아니라 확인해 볼 것">
        {d.cautions.length ? (
          <ul className="space-y-1 text-[12.5px]">
            {d.cautions.map((x, i) => (
              <li key={i} className="flex gap-2"><span style={{ color: WARN }}>⚠</span>
                <span style={{ color: SECONDARY }}>{x.text}<span className="ml-1.5 text-[11.5px]" style={{ color: FAINT }}>{x.why}</span></span></li>
            ))}
          </ul>
        ) : <p className="text-[12.5px]" style={{ color: MUTED }}>저장된 데이터에서 걸리는 것은 없습니다. 반대 의견은 증권사 리포트·기사에서 직접 찾아보세요(가이드 2-6).</p>}
      </Section>

      {/* ⑤ 내 기록 */}
      <Section title={<><Step n="3">{null}</Step>내 기록</>} sub="메모 · 정성 체크 · 관찰 노트">
        {d.mine?.note
          ? <p className="text-[12.5px] whitespace-pre-line rounded-lg p-2.5" style={{ background: "var(--bg-inset)", color: SECONDARY }}>{d.mine.note}</p>
          : <p className="text-[12.5px]" style={{ color: MUTED }}>{d.mine ? "메모 없음 - 워치리스트 팝업에서 적을 수 있습니다" : "내 워치리스트에 없는 종목입니다"}</p>}
        <div className="mt-3"><ChecklistSection c={c} /></div>
        <div className="mt-3 text-[12.5px]">
          {d.notes.length > 0 && (
            <div className="mb-2 space-y-0.5">
              {d.notes.map((n) => (
                <p key={n.id} style={{ color: SECONDARY }}><span style={{ color: FAINT }}>{n.created_at.slice(0, 10)}</span> {n.hypothesis}</p>
              ))}
              <Link href="/notes" className="underline text-[12px]" style={{ color: INFO }}>관찰 노트에서 회고 보기</Link>
            </div>
          )}
          <button onClick={() => setObsOpen(true)} className="px-3 py-1 rounded text-[12.5px]" style={{ border: "1px solid #453b1f", color: ACCENT }}>
            + 관찰 노트에 기대 남기기</button>
        </div>
        {obsOpen && (
          <ObservationForm kind="stock" market={d.market} ticker={d.symbol} title={`${d.name ?? d.symbol} 관찰 노트`}
            onClose={() => setObsOpen(false)} onSaved={() => setObsOpen(false)} />
        )}
      </Section>
    </div>
  );
}

export default function CompanyPage() {
  return (
    <Suspense fallback={<p className="text-[13px] p-6" style={{ color: MUTED }}>불러오는 중...</p>}>
      <CompanyView />
    </Suspense>
  );
}
