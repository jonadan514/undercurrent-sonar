"use client";

import { useEffect, useState } from "react";
import FlagIcon from "@/src/components/FlagIcon";
import StockLink from "@/src/components/StockLink";
import { themeName } from "@/src/lib/themeNames";
import { TagBadges } from "@/src/components/TagBadge";
import AsOf from "@/src/components/AsOf";
import { labelWithKo } from "@/src/lib/labelNames";

interface StockRef {
  market: string;
  symbol: string;
  name?: string | null;
  fit_score?: number | null;
  path?: string;
  catalysts?: string[];
}
interface MarketWeek {
  index_chg_1w: number | null;
}
interface ThemeLabelChange { theme_id: string; label: string; market?: "US" | "KR" }
interface ThemeLabelChanges { week_start: string | null; new_labels: ThemeLabelChange[]; dropped_labels: ThemeLabelChange[] }
interface Briefing {
  week: string;
  generated_at: string;
  us: MarketWeek;
  kr: MarketWeek;
  // added_count/removed_count: 자르기 전 전체 건수(2026-10-05부터). 예전 브리핑에는 없어 목록 길이로 대신한다.
  watchlist: { total: number; added: StockRef[]; removed: StockRef[]; top: StockRef[]; has_prev: boolean; added_count?: number; removed_count?: number };
  sentiment_heating: StockRef[];
  catalysts: StockRef[];
  gpt_comment: string;
  theme_labels?: ThemeLabelChanges;
  // 금리·환율 1주 변화(2026-10-05부터, macro_snapshot 그대로). 예전 브리핑엔 없다.
  // dxy·wti는 2026-10-09부터
  macro?: { as_of?: string; us10y?: MacroItem | null; kr3y?: MacroItem | null; usdkrw?: MacroItem | null;
            dxy?: MacroItem | null; wti?: MacroItem | null; copper?: MacroItem | null;   // copper는 2026-10-17부터
            natgas?: MacroItem | null; hy_spread?: MacroItem | null; real10y?: MacroItem | null } | null;   // 2026-10-17 밤부터
  // 워치리스트 '실적 반전'(3년 정체·역성장인데 지금 흐름 성장) 주간 변동(2026-10-17부터). 예전 브리핑엔 없다.
  kr_flows?: Record<string, FlowSum> | null;
  turnaround?: { total: number; by_market: Record<string, number>; has_prev: boolean;
                 added: TurnaroundItem[]; added_count: number; removed: StockRef[]; removed_count: number } | null;
  earnings_week?: { total: number; by_market: Record<string, number>; tagged_count: number; items: EarningsItem[] } | null;
  // termination(계약 해지)·amend(계약금액 정정)는 2026-10-21부터
  kr_disclosures?: { contract: { count: number; items: DisclosureItem[] }; prelim: { count: number; items: DisclosureItem[] };
                     termination?: { count: number; items: DisclosureItem[] }; amend?: { count: number; items: DisclosureItem[] } } | null;
}
// 한국 공시 지난 7일(2026-10-17부터, DART 원문 표 값 그대로). 유니버스(시총 3000억+) 또는 관심 표시 종목만.
interface DisclosureItem { symbol: string; name?: string | null; date: string; rcept_no: string; tags: string[]; summary: string;
  amount_before?: number | null; amount_after?: number | null; pct_before?: number | null; pct_after?: number | null;
  amount?: number | null; pct?: number | null; title?: string | null; withheld?: boolean; quarter?: string;
  revenue_yoy_pct?: number | null; revenue_yoy_turn?: string | null; operating_income_yoy_pct?: number | null; operating_income_yoy_turn?: string | null }
const eok = (v?: number | null) => v == null ? "-" : Math.abs(v) >= 1e12 ? `${(v / 1e12).toFixed(1)}조` : Math.abs(v) >= 1e8 ? `${Math.round(v / 1e8).toLocaleString()}억` : `${(v / 1e8).toFixed(1)}억`;
function YoY({ label, pct, turn }: { label: string; pct?: number | null; turn?: string | null }) {
  if (turn) return <span>{label} <span style={{ color: turn.startsWith("흑자") ? "#4ade80" : "#f87171" }}>{turn}</span></span>;
  if (pct == null) return <span style={{ color: "var(--text-muted)" }}>{label} -</span>;
  return <span>{label} <span style={{ color: pct >= 0 ? "#4ade80" : "#f87171" }}>{pct >= 0 ? "+" : ""}{pct.toFixed(0)}%</span></span>;
}
// 이름은 종목 상세로, 옆 "원문"은 DART 공시로(2026-10-20)
function DiscName({ d }: { d: DisclosureItem }) {
  return (
    <span className="inline-flex items-center gap-1">
      <StockLink market="KR" symbol={d.symbol} className="font-bold text-white inline-flex items-center gap-1">
        <FlagIcon market="KR" size={11} />{d.name || d.symbol}
      </StockLink>
      <a href={`https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${d.rcept_no}`} target="_blank" rel="noreferrer"
        className="text-[11px] hover:underline" style={{ color: "var(--text-muted)" }}>원문↗</a>
    </span>
  );
}
function discTotal(b: { kr_disclosures?: Briefing["kr_disclosures"] }): number {
  const k = b.kr_disclosures;
  return k ? k.contract.count + k.prelim.count + (k.termination?.count ?? 0) + (k.amend?.count ?? 0) : 0;
}
function DiscTags({ tags }: { tags: string[] }) {
  return <TagBadges tags={tags} />;
}
// 코스피·코스닥 투자자별 순매수 최근 5거래일 합(원, 2026-10-17부터). 예전 브리핑엔 없다.
interface FlowSum { foreign?: number; institution?: number; individual?: number; days: number; from: string; to: string }
const fmtFlow = (v?: number) => v == null ? "-" : Math.abs(v) >= 1e12
  ? `${v >= 0 ? "+" : ""}${(v / 1e12).toFixed(1)}조` : `${v >= 0 ? "+" : ""}${Math.round(v / 1e8).toLocaleString()}억`;
function FlowRow({ label, f }: { label: string; f?: FlowSum | null }) {
  if (!f) return null;
  const part = (name: string, v?: number) => (
    <span>{name} <span style={{ color: v == null ? "var(--text-muted)" : v >= 0 ? "#4ade80" : "#f87171" }}>{fmtFlow(v)}</span></span>
  );
  return (
    <div className="flex items-center gap-3 flex-wrap rounded-lg px-3 py-2" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
      <span className="text-[13px] font-bold text-white w-24 shrink-0">{label}</span>
      <span className="text-[12px] flex gap-3 flex-wrap" style={{ color: "var(--text-secondary)" }}>
        {part("외국인", f.foreign)}{part("기관", f.institution)}{part("개인", f.individual)}
      </span>
      <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>최근 {f.days}거래일 순매수</span>
    </div>
  );
}
// 이번 주 실적 발표 예정(2026-10-17부터, earnings_calendar - yfinance). 예상이면 date~date_end 범위.
interface EarningsItem { market: string; symbol: string; name?: string | null; date: string; date_end: string; estimate: boolean; tags: string[] }
const WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"];
const mdw = (d: string) => { const [y, m, dd] = d.split("-").map(Number); return `${m}/${dd}(${WEEKDAY[new Date(y, m - 1, dd).getDay()]})`; };
interface TurnaroundItem { market: string; symbol: string; name?: string | null; basis: "1년" | "분기"; yoy: number | null }
interface MacroItem { value: number | null; chg_1w: number | null }

// 매크로는 줄마다 한 칸씩이면 9줄이 넘어 브리핑이 길어진다 - 작은 칸으로 묶는다(2026-10-20)
function MacroRow({ label, m, fmt, chgFmt }: { label: string; m?: MacroItem | null; fmt: (v: number) => string; chgFmt: (v: number) => string }) {
  if (!m || m.value == null) return null;
  return (
    <div className="rounded-lg px-2.5 py-1.5" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
      <p className="text-[11px] truncate" style={{ color: "var(--text-muted)" }}>{label}</p>
      <p className="text-[13px] font-bold text-white" style={{ fontVariantNumeric: "tabular-nums" }}>{fmt(m.value)}</p>
      {m.chg_1w != null && (
        <p className="text-[11px]" style={{ color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>주간 {chgFmt(m.chg_1w)}</p>
      )}
    </div>
  );
}

function StockLabel({ s }: { s: StockRef }) {
  return (
    <StockLink market={s.market} symbol={s.symbol} className="inline-flex items-center gap-1">
      <FlagIcon market={s.market as "US" | "KR"} size={11} />
      <span className="font-bold text-white">{s.market === "KR" ? (s.name || s.symbol) : s.symbol}</span>
    </StockLink>
  );
}

function MarketRow({ label, m }: { label: string; m: MarketWeek }) {
  return (
    <div className="flex items-center gap-3 flex-wrap rounded-lg px-3 py-2" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
      <span className="text-[13px] font-bold text-white w-24 shrink-0">{label}</span>
      {m.index_chg_1w != null ? (
        <span className="text-[12px] font-bold" style={{ color: m.index_chg_1w >= 0 ? "#4ade80" : "#f87171" }}>
          주간 {m.index_chg_1w >= 0 ? "+" : ""}{m.index_chg_1w}%
        </span>
      ) : (
        <span className="text-[12px]" style={{ color: "var(--text-faint)" }}>—</span>
      )}
    </div>
  );
}

function BriefingCard({ b, defaultOpen }: { b: Briefing; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const wl = b.watchlist ?? { total: 0, added: [], removed: [], top: [], has_prev: false };
  // 목차(2026-10-20) - 최신 주는 개요 "이번 주 변화"가 쓰는 짧은 앵커(#earnings 등), 지난 주는 주차를 붙여 겹치지 않게
  const sid = (k: string) => defaultOpen ? k : `${b.week}-${k}`;
  const toc: [string, string][] = [
    ["market", "지난주 시장"],
    ...(b.theme_labels && (b.theme_labels.new_labels.length > 0 || b.theme_labels.dropped_labels.length > 0) ? [["labels", "테마 라벨"] as [string, string]] : []),
    ...(b.gpt_comment ? [["comment", "총평"] as [string, string]] : []),
    ["watchlist", "워치리스트"],
    ...(b.turnaround ? [["turnaround", "실적 반전"] as [string, string]] : []),
    ...(b.earnings_week && b.earnings_week.total > 0 ? [["earnings", "실적 발표"] as [string, string]] : []),
    ...(discTotal(b) > 0 ? [["disclosures", "한국 공시"] as [string, string]] : []),
    ...(b.sentiment_heating?.length > 0 ? [["sentiment", "관심도"] as [string, string]] : []),
    ...(b.catalysts?.length > 0 ? [["catalysts", "촉매"] as [string, string]] : []),
  ];

  return (
    <div className="bg-card rounded-xl overflow-hidden">
      <button className="w-full flex items-center gap-3 px-4 py-3 text-left" onClick={() => setOpen(!open)}>
        <span className="text-[14px] font-bold text-white">📋 {b.week} 주</span>
        <span className="text-[11px]" style={{ color: "var(--text-faint)" }}>{b.generated_at}</span>
        <span className="ml-auto text-[12px]" style={{ color: "#ffb020" }}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4" style={{ borderTop: "1px solid var(--border)" }}>
          {/* 목차 */}
          <nav className="pt-3 flex flex-wrap gap-1.5" aria-label="브리핑 목차">
            {toc.map(([k, label]) => (
              <a key={k} href={`#${sid(k)}`} className="text-[11px] px-2 py-0.5 rounded hover:brightness-125"
                style={{ background: "var(--bg-inset)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>{label}</a>
            ))}
          </nav>
          {/* 시장 궤적 */}
          <div id={sid("market")} className="space-y-1.5" style={{ scrollMarginTop: 72 }}>
            <p className="text-[12px] font-bold" style={{ color: "var(--text-muted)" }}>지난주 시장</p>
            <MarketRow label="🇺🇸 S&P 500" m={b.us} />
            <MarketRow label="🇰🇷 KOSPI" m={b.kr} />
            <FlowRow label="코스피 수급" f={b.kr_flows?.KOSPI} />
            <FlowRow label="코스닥 수급" f={b.kr_flows?.KOSDAQ} />
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-1.5">
            <MacroRow label="미 10년물" m={b.macro?.us10y}
              fmt={(v) => `${v.toFixed(2)}%`} chgFmt={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%p`} />
            <MacroRow label="미 실질금리" m={b.macro?.real10y}
              fmt={(v) => `${v.toFixed(2)}%`} chgFmt={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%p`} />
            <MacroRow label="하이일드 스프레드" m={b.macro?.hy_spread}
              fmt={(v) => `${v.toFixed(2)}%p`} chgFmt={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%p`} />
            <MacroRow label="국고채 3년" m={b.macro?.kr3y}
              fmt={(v) => `${v.toFixed(2)}%`} chgFmt={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%p`} />
            <MacroRow label="원/달러" m={b.macro?.usdkrw}
              fmt={(v) => `${Math.round(v).toLocaleString()}원`} chgFmt={(v) => `${v >= 0 ? "+" : ""}${Math.round(v).toLocaleString()}원`} />
            <MacroRow label="달러인덱스" m={b.macro?.dxy}
              fmt={(v) => v.toFixed(1)} chgFmt={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}`} />
            <MacroRow label="WTI 유가" m={b.macro?.wti}
              fmt={(v) => `$${v.toFixed(1)}`}
              chgFmt={(v) => {
                const base = (b.macro?.wti?.value ?? 0) - v;
                const pct = base ? ` (${v / base >= 0 ? "+" : ""}${(v / base * 100).toFixed(1)}%)` : "";
                return `${v >= 0 ? "+" : "-"}$${Math.abs(v).toFixed(2)}${pct}`;
              }} />
            <MacroRow label="구리" m={b.macro?.copper}
              fmt={(v) => `$${v.toFixed(2)}/lb`}
              chgFmt={(v) => {
                const base = (b.macro?.copper?.value ?? 0) - v;
                const pct = base ? ` (${v / base >= 0 ? "+" : ""}${(v / base * 100).toFixed(1)}%)` : "";
                return `${v >= 0 ? "+" : "-"}$${Math.abs(v).toFixed(2)}${pct}`;
              }} />
            <MacroRow label="천연가스" m={b.macro?.natgas}
              fmt={(v) => `$${v.toFixed(2)}`}
              chgFmt={(v) => {
                const base = (b.macro?.natgas?.value ?? 0) - v;
                const pct = base ? ` (${v / base >= 0 ? "+" : ""}${(v / base * 100).toFixed(1)}%)` : "";
                return `${v >= 0 ? "+" : "-"}$${Math.abs(v).toFixed(2)}${pct}`;
              }} />
            </div>
          </div>

          {/* 테마 레이더 라벨 변동 — 라벨 계산은 별도 워크플로우라 이 브리핑보다 늦게
              끝날 수 있어서, "이번 주"라 단정하지 않고 실제 기준 주를 그대로 보여준다. */}
          {b.theme_labels && (b.theme_labels.new_labels.length > 0 || b.theme_labels.dropped_labels.length > 0) && (
            <div id={sid("labels")} style={{ scrollMarginTop: 72 }}>
              <p className="text-[12px] font-bold mb-1.5" style={{ color: "var(--text-muted)" }}>
                📡 테마 레이더 라벨 변동 <span style={{ color: "var(--text-faint)" }}>({b.theme_labels.week_start} 기준)</span>
              </p>
              <div className="rounded-xl p-3 space-y-2" style={{ background: "#ffb02008", border: "1px solid #ffb02022" }}>
                {b.theme_labels.new_labels.length > 0 && (
                  <div>
                    <p className="text-[11px] font-bold mb-1" style={{ color: "#ffb020" }}>+ 신규 라벨 ({b.theme_labels.new_labels.length})</p>
                    {b.theme_labels.new_labels.map((t) => (
                      <p key={`${t.market ?? "US"}:${t.theme_id}`} className="text-[12px] py-0.5">
                        <span className="mr-1">{t.market === "KR" ? "🇰🇷" : "🇺🇸"}</span>
                        <span className="font-bold text-white">{themeName(t.theme_id).ko}</span>
                        <span className="ml-1.5" style={{ color: "var(--text-muted)" }}>{labelWithKo(t.label)}</span>
                      </p>
                    ))}
                  </div>
                )}
                {b.theme_labels.dropped_labels.length > 0 && (
                  <div>
                    <p className="text-[11px] font-bold mb-1" style={{ color: "var(--text-faint)" }}>− 소멸 라벨 ({b.theme_labels.dropped_labels.length})</p>
                    {b.theme_labels.dropped_labels.map((t) => (
                      <p key={`${t.market ?? "US"}:${t.theme_id}`} className="text-[12px] py-0.5" style={{ color: "var(--text-faint)" }}>
                        {t.market === "KR" ? "🇰🇷" : "🇺🇸"} {themeName(t.theme_id).ko} <span>({labelWithKo(t.label)})</span>
                      </p>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* GPT 총평 */}
          {b.gpt_comment && (
            <div id={sid("comment")} className="rounded-xl p-3" style={{ scrollMarginTop: 72, background: "#ffb02008", border: "1px solid #ffb02022" }}>
              <p className="text-[12px] font-bold mb-1.5" style={{ color: "#ffb020" }}>주간 총평</p>
              <p className="text-[12px] leading-relaxed whitespace-pre-line" style={{ color: "#a39c88" }}>{b.gpt_comment}</p>
            </div>
          )}

          {/* 워치리스트 변동 */}
          <div id={sid("watchlist")} style={{ scrollMarginTop: 72 }}>
            <p className="text-[12px] font-bold mb-1.5" style={{ color: "var(--text-muted)" }}>
              워치리스트 변동 <span style={{ color: "var(--text-faint)" }}>(후보 {wl.total}개)</span>
            </p>
            {!wl.has_prev ? (
              <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>첫 스냅샷 주간 — 다음 주부터 신규/탈락 비교가 표시돼요.</p>
            ) : wl.added.length === 0 && wl.removed.length === 0 ? (
              <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>변동 없음</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <div className="rounded-lg p-2.5" style={{ background: "var(--bg-inset)", border: "1px solid #ffb02022" }}>
                  <p className="text-[11px] font-bold mb-1" style={{ color: "#ffb020" }}>+ 신규 진입 ({wl.added_count ?? wl.added.length})</p>
                  {wl.added.map((s) => (
                    <p key={`${s.market}:${s.symbol}`} className="text-[12px] py-0.5">
                      <StockLabel s={s} />
                      {s.fit_score != null && <span className="ml-1.5" style={{ color: "var(--text-muted)" }}>적합 {s.fit_score}</span>}
                    </p>
                  ))}
                  {wl.added.length === 0 && <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>없음</p>}
                  {(wl.added_count ?? 0) > wl.added.length && <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>외 {(wl.added_count ?? 0) - wl.added.length}개 - 워치리스트 &quot;이번 회차 신규만&quot;에서 전체 보기</p>}
                </div>
                <div className="rounded-lg p-2.5" style={{ background: "var(--bg-inset)", border: "1px solid #f8717122" }}>
                  <p className="text-[11px] font-bold mb-1" style={{ color: "#f87171" }}>− 탈락 ({wl.removed_count ?? wl.removed.length})</p>
                  {wl.removed.map((s) => (
                    <p key={`${s.market}:${s.symbol}`} className="text-[12px] py-0.5"><StockLabel s={s} /></p>
                  ))}
                  {wl.removed.length === 0 && <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>없음</p>}
                  {(wl.removed_count ?? 0) > wl.removed.length && <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>외 {(wl.removed_count ?? 0) - wl.removed.length}개</p>}
                </div>
              </div>
            )}
          </div>

          {/* 실적 반전 - 워치리스트 같은 이름 버튼과 같은 조건 */}
          {b.turnaround && (
            <div id={sid("turnaround")} style={{ scrollMarginTop: 72 }}>
              <p className="text-[12px] font-bold mb-1.5" style={{ color: "var(--text-muted)" }}>
                실적 반전 — {Object.entries(b.turnaround.by_market).sort(([a], [c]) => c.localeCompare(a)).map(([m, n]) => `${m === "KR" ? "한국" : "미국"} ${n}`).join(" · ") || "0"}
                {b.turnaround.has_prev && <> · 새로 {b.turnaround.added_count} · 빠짐 {b.turnaround.removed_count}</>}
              </p>
              {b.turnaround.added.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {b.turnaround.added.map((s) => (
                    <span key={`${s.market}:${s.symbol}`} className="text-[12px] px-2 py-1 rounded-lg"
                      style={{ background: "#4ade8012", border: "1px solid #4ade8033" }}>
                      <StockLabel s={s} />
                      {s.yoy != null && <span style={{ color: "#4ade80" }}> {s.basis} {s.yoy >= 0 ? "+" : ""}{(s.yoy * 100).toFixed(0)}%</span>}
                    </span>
                  ))}
                  {b.turnaround.added_count > b.turnaround.added.length && (
                    <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>외 {b.turnaround.added_count - b.turnaround.added.length}개</span>
                  )}
                </div>
              ) : (
                <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>
                  {b.turnaround.has_prev ? "이번 주 새로 들어온 종목 없음" : "새로 들어온 종목 비교는 다음 주부터"}
                </p>
              )}
              <p className="text-[11px] mt-1" style={{ color: "var(--text-muted)" }}>
                매출 3년은 정체·역성장인데 최근 1년(4개 분기 합, 없으면 최근 분기)은 성장 — 워치리스트 &quot;실적 반전&quot; 버튼과 같은 조건
              </p>
            </div>
          )}

          {/* 이번 주 실적 발표 - 워치리스트·내 관심·관찰 노트 종목 */}
          {b.earnings_week && b.earnings_week.total > 0 && (
            <div id={sid("earnings")} style={{ scrollMarginTop: 72 }}>
              <p className="text-[12px] font-bold mb-1.5" style={{ color: "var(--text-muted)" }}>
                이번 주 실적 발표 — {Object.entries(b.earnings_week.by_market).sort(([a], [c]) => c.localeCompare(a)).map(([m, n]) => `${m === "KR" ? "한국" : "미국"} ${n}`).join(" · ")}
              </p>
              <div className="space-y-1.5">
                {Array.from(new Set(b.earnings_week.items.map((x) => x.date))).map((d) => (
                  <div key={d} className="flex items-start gap-2">
                    <span className="text-[12px] font-bold text-white w-20 shrink-0 pt-1 whitespace-nowrap">{mdw(d)}</span>
                    <div className="flex flex-wrap gap-1.5">
                      {b.earnings_week!.items.filter((x) => x.date === d)
                        .sort((x, y) => Number(y.tags.length > 0) - Number(x.tags.length > 0))
                        .map((x) => (
                          <span key={`${x.market}:${x.symbol}`} className="text-[12px] px-2 py-1 rounded-lg"
                            style={x.tags.length > 0
                              ? { background: "#f59e0b14", border: "1px solid #f59e0b55" }
                              : { background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                            <StockLabel s={x} />
                            {x.tags.length > 0 && <> <TagBadges tags={x.tags} /></>}
                            {x.estimate && <span style={{ color: "var(--text-muted)" }}> 예상{x.date_end !== x.date ? `~${mdw(x.date_end)}` : ""}</span>}
                          </span>
                        ))}
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-[11px] mt-1" style={{ color: "var(--text-muted)" }}>
                워치리스트 후보·내 관심·관찰 노트 종목 · 날짜는 yfinance(회사 공지 전이면 &quot;예상&quot;), 한국은 결산실적 공시예고가 있으면 그 날짜 · 노란 칸이 내 관심·노트·실적 반전
              </p>
            </div>
          )}

          {/* 한국 공시 지난 7일 - 공급계약·잠정실적 */}
          {b.kr_disclosures && discTotal(b) > 0 && (
            <div id={sid("disclosures")} style={{ scrollMarginTop: 72 }}>
              <p className="text-[12px] font-bold mb-1.5" style={{ color: "var(--text-muted)" }}>
                한국 공시 (지난 7일) — 공급계약 {b.kr_disclosures.contract.count} · 잠정실적 {b.kr_disclosures.prelim.count}
                {(b.kr_disclosures.termination?.count ?? 0) > 0 && <> · 계약 해지 {b.kr_disclosures.termination!.count}</>}
                {(b.kr_disclosures.amend?.count ?? 0) > 0 && <> · 금액 정정 {b.kr_disclosures.amend!.count}</>}
              </p>
              {b.kr_disclosures.contract.items.length > 0 && (
                <div className="mb-2">
                  <p className="text-[11px] mb-1" style={{ color: "var(--text-muted)" }}>공급계약 · 관심 종목 먼저, 그다음 매출 대비 큰 순</p>
                  <div className="space-y-1">
                    {b.kr_disclosures.contract.items.map((d) => (
                      <div key={d.rcept_no} className="flex items-center gap-2 flex-wrap text-[12px] rounded-lg px-3 py-1.5"
                        style={d.tags.length > 0 ? { background: "#f59e0b14", border: "1px solid #f59e0b55" } : { background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                        <span className="w-11 shrink-0 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>{d.date.slice(5).replace("-", "/")}</span>
                        <DiscName d={d} />
                        <span className="text-white">{d.withheld ? "금액 비공개" : eok(d.amount)}</span>
                        {d.pct != null && <span style={{ color: d.pct >= 10 ? "#4ade80" : "var(--text-secondary)" }}>매출 대비 {d.pct.toFixed(1)}%</span>}
                        {d.title && <span className="truncate max-w-[16rem]" style={{ color: "var(--text-secondary)" }}>{d.title}</span>}
                        <DiscTags tags={d.tags} />
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {((b.kr_disclosures.termination?.items.length ?? 0) + (b.kr_disclosures.amend?.items.length ?? 0)) > 0 && (
                <div className="mb-2">
                  <p className="text-[11px] mb-1" style={{ color: "var(--text-muted)" }}>계약 해지 · 계약금액 정정 (날짜만 바뀐 정정은 뺌)</p>
                  <div className="space-y-1">
                    {[...(b.kr_disclosures.termination?.items ?? []), ...(b.kr_disclosures.amend?.items ?? [])].map((d) => (
                      <div key={d.rcept_no} className="flex items-center gap-2 flex-wrap text-[12px] rounded-lg px-3 py-1.5"
                        style={{ background: "#f8717110", border: `1px solid ${d.tags.length > 0 ? "#f59e0b55" : "#f8717133"}` }}>
                        <span className="w-11 shrink-0 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>{d.date.slice(5).replace("-", "/")}</span>
                        <DiscName d={d} />
                        <span style={{ color: "#fca5a5" }}>{d.summary}</span>
                        <DiscTags tags={d.tags} />
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {b.kr_disclosures.prelim.items.length > 0 && (
                <div>
                  <p className="text-[11px] mb-1" style={{ color: "var(--text-muted)" }}>잠정실적 · 전년 같은 분기 대비, 회사가 공시한 증감률</p>
                  <div className="space-y-1">
                    {b.kr_disclosures.prelim.items.map((d) => (
                      <div key={d.rcept_no} className="flex items-center gap-2 flex-wrap text-[12px] rounded-lg px-3 py-1.5"
                        style={d.tags.length > 0 ? { background: "#f59e0b14", border: "1px solid #f59e0b55" } : { background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                        <span className="w-11 shrink-0 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>{d.date.slice(5).replace("-", "/")}</span>
                        <DiscName d={d} />
                        {d.quarter && <span style={{ color: "var(--text-muted)" }}>{d.quarter}</span>}
                        <YoY label="매출" pct={d.revenue_yoy_pct} turn={d.revenue_yoy_turn} />
                        <YoY label="영업익" pct={d.operating_income_yoy_pct} turn={d.operating_income_yoy_turn} />
                        <DiscTags tags={d.tags} />
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {(b.kr_disclosures.contract.count > b.kr_disclosures.contract.items.length || b.kr_disclosures.prelim.count > b.kr_disclosures.prelim.items.length) && (
                <p className="text-[11px] mt-1" style={{ color: "var(--text-muted)" }}>목록은 종류별 30건까지</p>
              )}
              <p className="text-[11px] mt-1" style={{ color: "var(--text-muted)" }}>
                시총 3000억 이상 또는 관심 종목(내 관심·노트·워치리스트·테마) · 정정·자회사 공시 제외 · 이름을 누르면 종목 상세, 원문↗은 DART 공시
              </p>
            </div>
          )}

          {/* 관심도 상승 */}
          {b.sentiment_heating?.length > 0 && (
            <div id={sid("sentiment")} style={{ scrollMarginTop: 72 }}>
              <p className="text-[12px] font-bold mb-1.5" style={{ color: "var(--text-muted)" }}>관심도 상승</p>
              <div className="flex flex-wrap gap-2">
                {b.sentiment_heating.map((s) => (
                  <span key={`${s.market}:${s.symbol}`} className="text-[12px] px-2 py-1 rounded-lg"
                    style={{ background: "#f8717112", border: "1px solid #f8717133" }}>
                    <StockLabel s={s} /> <span style={{ color: "#f87171" }}>{s.path}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 다가오는 촉매 */}
          {b.catalysts?.length > 0 && (
            <div id={sid("catalysts")} style={{ scrollMarginTop: 72 }}>
              <p className="text-[12px] font-bold mb-1.5" style={{ color: "var(--text-muted)" }}>
                내 워치리스트 — 다가오는 촉매
              </p>
              <div className="space-y-1.5">
                {b.catalysts.map((s) => (
                  <div key={`${s.market}:${s.symbol}`} className="rounded-lg px-3 py-2" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                    <StockLabel s={s} />
                    {(s.catalysts ?? []).map((c, i) => (
                      <p key={i} className="text-[12px] mt-0.5 pl-1" style={{ color: "var(--text-muted)" }}>▲ {c}</p>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function BriefingPage() {
  const [briefings, setBriefings] = useState<Briefing[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/briefing")
      .then((r) => r.json())
      .then((d) => setBriefings(d.briefings ?? []))
      .finally(() => setLoading(false));
  }, []);

  // 개요 "이번 주 변화"에서 #earnings 등으로 들어오면, 브리핑을 불러온 뒤에야 그 칸이 생긴다 - 그때 스크롤한다.
  useEffect(() => {
    if (loading || !window.location.hash) return;
    const el = document.getElementById(decodeURIComponent(window.location.hash.slice(1)));
    if (el) requestAnimationFrame(() => el.scrollIntoView({ block: "start" }));
  }, [loading]);

  return (
    <div className="space-y-3 max-w-3xl">
      <div>
        <div className="flex items-center gap-2 flex-wrap">
          <h1 className="text-base font-bold text-white">주간 브리핑</h1>
          {!loading && <AsOf date={briefings[0]?.week} cadence="매주 월요일 아침" staleDays={8} />}
        </div>
        <p className="text-[12px] mt-0.5" style={{ color: "var(--text-muted)" }}>
          매주 월요일 아침, 지난주를 돌아보고 이번 주를 준비하는 문서 — 위 목차를 눌러 칸으로 바로 이동
        </p>
      </div>

      {loading ? (
        <div className="h-24 rounded-xl animate-pulse" style={{ background: "#111009" }} />
      ) : briefings.length === 0 ? (
        <div className="bg-card rounded-xl p-6 text-center">
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>아직 브리핑이 없어요.</p>
          <p className="text-[12px] mt-1" style={{ color: "var(--text-faint)" }}>
            매주 일요일 밤 워치리스트 스크리닝 후 자동 생성됩니다. 지금 만들려면:
            GitHub → Actions → Weekly Watchlist Screen → Run workflow
          </p>
        </div>
      ) : (
        briefings.map((b, i) => <BriefingCard key={b.week} b={b} defaultOpen={i === 0} />)
      )}
    </div>
  );
}
