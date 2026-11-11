"use client";

import { Children, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import FlagIcon from "@/src/components/FlagIcon";
import StockLink from "@/src/components/StockLink";
import { themeName } from "@/src/lib/themeNames";
import { TagBadges } from "@/src/components/TagBadge";
import AsOf from "@/src/components/AsOf";
import { labelWithKo } from "@/src/lib/labelNames";
import PageHeader from "@/src/components/PageHeader";
import Note from "@/src/components/Note";
import EmptyState from "@/src/components/EmptyState";
import { ObservationForm } from "@/src/components/Observation";
import { Section } from "@/src/components/Section";
import { krStockName } from "@/src/lib/krStockNames";
import { BigChart, type Point, upTo, weekWindow, WeekSpark } from "@/src/components/MacroChart";
import { STYLE_META, type InvestorStyle } from "@/src/lib/institutions";

interface StockRef {
  market: string;
  symbol: string;
  name?: string | null;
  fit_score?: number | null;
  path?: string;
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
  gpt_comment: string;
  // 짚을 점 소제목 -> 관련 기사(2026-11-03). 코드가 고른 원문 제목·링크 - GPT를 거치지 않는다
  comment_news?: Record<string, { title: string; url: string; source: string; published_at: string }[]>;
  theme_labels?: ThemeLabelChanges;
  // 금리·환율 1주 변화(2026-10-05부터, macro_snapshot 그대로). 예전 브리핑엔 없다.
  // dxy·wti는 2026-10-09부터
  macro?: { as_of?: string; us10y?: MacroItem | null; kr3y?: MacroItem | null; usdkrw?: MacroItem | null;
            dxy?: MacroItem | null; wti?: MacroItem | null; copper?: MacroItem | null;   // copper는 2026-10-17부터
            natgas?: MacroItem | null; hy_spread?: MacroItem | null; real10y?: MacroItem | null;   // 2026-10-17 밤부터
            vix?: MacroItem | null; spread_10y_2y?: MacroItem | null } | null;   // 2026-11-05부터
  // 워치리스트 '실적 반전'(3년 정체·역성장인데 지금 흐름 성장) 주간 변동(2026-10-17부터). 예전 브리핑엔 없다.
  kr_flows?: Record<string, FlowSum> | null;
  // 시장 환경 축(2026-11-07부터, market_regime_weekly 그 주 값) - 축별 방향 + 정해진 조합 이름. 예전 브리핑엔 없다.
  regime?: Partial<Record<"US" | "KR", RegimeWeek>> | null;
  turnaround?: { total: number; by_market: Record<string, number>; has_prev: boolean;
                 added: TurnaroundItem[]; added_count: number; removed: StockRef[]; removed_count: number } | null;
  earnings_week?: { total: number; by_market: Record<string, number>; tagged_count: number; items: EarningsItem[] } | null;
  // termination(계약 해지)·amend(계약금액 정정)는 2026-10-21부터
  kr_disclosures?: { contract: { count: number; items: DisclosureItem[] }; prelim: { count: number; items: DisclosureItem[] };
                     termination?: { count: number; items: DisclosureItem[] }; amend?: { count: number; items: DisclosureItem[] } } | null;
  // tagged_count·discovery(관심 밖 새 이름)는 2026-10-21부터 - 그 전 브리핑은 items 하나에 관심 표시 먼저 섞여 있다
  insider_week?: { total: number; by_market: Record<string, number>; items: InsiderItem[]; tagged_count?: number;
                   discovery?: InsiderItem[]; discovery_count?: number } | null;
  us_8k_week?: { total: number; by_kind: Record<string, number>; items: Us8kItem[] } | null;
  my_stocks_week?: { watched: number; count: number; items: MyStock[] } | null;
  // 유명 투자자 13F - 지난 7일 신고한 운용사(2026-10-25부터). 낸 곳이 없으면 null
  inst_13f_week?: { filers: number; items: InstItem[] } | null;
}
type InstPos = { ticker: string | null; issuer: string | null; name?: string | null; value: number | null; prev_value: number | null;
  weight: number | null; tags: string[]; finance?: { status: string; piotroski: number | null } | null };
type InstItem = { manager_id: string; name: string; style?: string | null; period: string; filed: string; compared: boolean;
  counts: { new: number; added: number; reduced: number; sold: number }; new: InstPos[]; sold: InstPos[] };
const usdM = (v: number | null) => v == null ? "-" : Math.abs(v) >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${Math.round(v / 1e6).toLocaleString()}M`;
const qLabel = (p: string) => `${p.slice(0, 4)} Q${Math.floor((Number(p.slice(5, 7)) - 1) / 3) + 1}`;
function InstChip({ x, sold }: { x: InstPos; sold?: boolean }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1 text-[12px] px-2 py-1 rounded-lg"
      style={x.tags.length > 0 ? { background: "#f59e0b14", border: "1px solid #f59e0b55" } : { background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
      {x.ticker ? <StockLabel s={{ market: "US", symbol: x.ticker }} /> : <span className="font-bold" style={{ color: "var(--text-secondary)" }}>{x.issuer}</span>}
      <span style={{ color: "var(--text-secondary)" }}>{sold ? `직전 ${usdM(x.prev_value)}` : usdM(x.value)}</span>
      {!sold && x.weight != null && <span style={{ color: "var(--text-muted)" }}>{(x.weight * 100).toFixed(1)}%</span>}
      {!sold && <FinanceTag f={x.finance ? { status: x.finance.status, piotroski: x.finance.piotroski, reasons: [] } : null} />}
      <DiscTags tags={x.tags} />
    </span>
  );
}
// 관심 종목에 생긴 일(2026-10-21) - 내 관심·노트 종목 줄만 아래 칸들에서 모은 것. 눌러서 그 칸으로.
interface MyStock { market: string; symbol: string; name?: string | null; tags: string[];
  events: { kind: string; text: string; anchor: string; date?: string | null; warn: boolean }[] }
// 미국 8-K 지난 7일(2026-10-21부터, SEC). 항목 번호로 나눈 종류 + 원문 첫머리(영어 그대로). warn은 해지·손상 등 종류 분류일 뿐 점수 아님.
interface Us8kItem { market: string; symbol: string; name?: string | null; date: string; url?: string | null; tags: string[]; warn: boolean;
  items: { item: string; label: string; warn: boolean; excerpt?: string | null }[] }
// 내부자 장내 매수 지난 7일(2026-10-21부터, SEC Form 4 · DART 임원ㆍ주요주주 소유보고). 공시 숫자 합계일 뿐 점수 아님.
interface InsiderItem { market: string; symbol: string; name?: string | null; owners: string[]; roles: string[]; buyers: number;
  value: number | null; trades: number; last_date: string | null; all_plan: boolean; tags: string[];
  finance?: { status: string; piotroski: number | null; reasons: string[] } | null }
// 재무 필터 3분류 - 계산 못 한 것은 탈락이 아니라 데이터 부족, 스크리닝 결과가 없으면 미확인(원칙 4)
function FinanceTag({ f }: { f?: InsiderItem["finance"] }) {
  const [label, color] = f?.status === "pass" ? [`재무 통과${f.piotroski != null ? ` F${f.piotroski}` : ""}`, "#4ade80"]
    : f?.status === "fail" ? ["재무 탈락", "#f87171"] : f?.status === "insufficient" ? ["데이터 부족", "var(--text-muted)"] : ["재무 미확인", "var(--text-muted)"];
  return <span className="text-[11px] px-1.5 rounded" style={{ color, border: "1px solid var(--border)" }} title={f?.reasons?.join(" / ") || undefined}>{label}</span>;
}
function InsiderRow({ x, showFinance = false, note }: { x: InsiderItem; showFinance?: boolean; note?: ReactNode }) {
  return (
    <div className={ROW} style={rowMark(x.tags.length > 0)}>
      <span className="w-11 shrink-0 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>{dayLabel(x.last_date)}</span>
      <StockLabel s={x} />
      <span className="text-white">{insiderMoney(x.value, x.market)}</span>
      <span style={{ color: x.buyers > 1 ? "#4ade80" : "var(--text-secondary)" }}>
        {x.buyers > 1 ? `${x.buyers}명` : x.owners[0]}{x.buyers === 1 && x.roles[0] && x.roles[0] !== "-" ? ` (${x.roles[0]})` : ""}
      </span>
      <span style={{ color: "var(--text-muted)" }}>{x.trades}건</span>
      {x.all_plan && <span style={{ color: "var(--text-muted)" }} title="10b5-1: 미리 정해 둔 계획 매수">계획 매수</span>}
      {showFinance && <FinanceTag f={x.finance} />}
      <DiscTags tags={x.tags} />
      {note}
    </div>
  );
}
const insiderMoney = (v: number | null, market: string) => v == null ? "-" : market === "KR" ? (v >= 1e8 ? `${eok(v)}원` : `${Math.round(v / 1e4).toLocaleString()}만원`)
  : v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : `$${Math.round(v / 1e3).toLocaleString()}K`;
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
      <StockLink market="KR" symbol={d.symbol} className="font-bold text-white">{d.name || d.symbol}</StockLink>
      <a href={`https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${d.rcept_no}`} target="_blank" rel="noreferrer" title="DART 공시 원문"
        className="text-[11px] hover:underline" style={{ color: "var(--text-faint)" }}>↗</a>
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
type MacroKey = "us10y" | "real10y" | "hy_spread" | "spread_10y_2y" | "kr3y" | "usdkrw" | "dxy" | "vix" | "wti" | "copper" | "natgas";
const pp = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%p`;
// ── 시장 환경 배지(2026-11-07) ─────────────────────────────────────────────
// 그 주 브리핑에 저장된 축 상태 - 조합 이름(정해진 것만)과 축별 4주 방향. 점수·판단 없음(원칙 1). 자세한 표는 개요 '시장 환경'.
interface RegimeWeek {
  week: string; as_of: string;
  axes: Record<string, { name: string; dir: string | null }>;
  combos: { id: string; name: string; meaning: string }[];
}
const RG_ARROW: Record<string, string> = { up: "↑", flat: "→", down: "↓" };
function RegimeBadges({ regime }: { regime: Partial<Record<"US" | "KR", RegimeWeek>> }) {
  const rows = (["US", "KR"] as const).filter((m) => regime[m]);
  if (!rows.length) return null;
  return (
    <div className="mb-2 rounded-lg px-3 py-2 space-y-1" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
      {rows.map((m) => {
        const r = regime[m]!;
        return (
          <div key={m} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px]">
            <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{m === "US" ? "🇺🇸 미국" : "🇰🇷 한국"} 시장 환경</span>
            {r.combos.length ? r.combos.map((c) => (
              <span key={c.id} className="rounded px-1.5 py-0.5 text-[12px] font-bold" style={{ background: "#ffb02022", color: "#ffb020" }} title={c.meaning}>{c.name}</span>
            )) : <span style={{ color: "var(--text-faint)" }}>정해진 조합 없음</span>}
            <span className="text-[11.5px]" style={{ color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
              {Object.values(r.axes).map((a) => `${a.name}${a.dir ? RG_ARROW[a.dir] : "·"}`).join(" ")}
            </span>
          </div>
        );
      })}
      <p className="text-[11px]" style={{ color: "var(--text-faint)" }}>
        최근 4주 방향(각 지표의 평소 4주 변화폭 대비) · 이름은 정해진 조합에만 · <a href="/#regime" className="underline">개요에서 자세히</a>
      </p>
    </div>
  );
}

const MACRO_ROWS: { key: MacroKey; label: string; fmt: (v: number) => string; chg?: (v: number) => string }[] = [
  { key: "us10y", label: "미 10년물", fmt: (v) => `${v.toFixed(2)}%`, chg: pp },
  { key: "real10y", label: "미 실질금리", fmt: (v) => `${v.toFixed(2)}%`, chg: pp },
  { key: "hy_spread", label: "하이일드 스프레드", fmt: (v) => `${v.toFixed(2)}%p`, chg: pp },
  { key: "spread_10y_2y", label: "장단기 금리차", fmt: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%p`, chg: pp },   // 미 10년-2년(2026-11-05)
  { key: "kr3y", label: "국고채 3년", fmt: (v) => `${v.toFixed(2)}%`, chg: pp },
  { key: "usdkrw", label: "원/달러", fmt: (v) => `${Math.round(v).toLocaleString()}원`, chg: (v) => `${v >= 0 ? "+" : ""}${Math.round(v).toLocaleString()}원` },
  { key: "dxy", label: "달러인덱스", fmt: (v) => v.toFixed(1), chg: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}` },
  { key: "vix", label: "VIX", fmt: (v) => v.toFixed(1), chg: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}` },   // 2026-11-05
  { key: "wti", label: "WTI 유가", fmt: (v) => `$${v.toFixed(1)}` },          // 유가·원자재는 변화율(usdChg)
  { key: "copper", label: "구리", fmt: (v) => `$${v.toFixed(2)}/lb` },
  { key: "natgas", label: "천연가스", fmt: (v) => `$${v.toFixed(2)}` },
];

// 매크로 칸(2026-11-02, 사용자 요청: 한 주 흐름을 그래프로) - 칸마다 그 주 선(앞 3주는 흐리게), 누르면 큰 그래프(그 주 음영, 그 주 끝까지).
// 값·주간 변화는 브리핑에 저장된 그대로, 선은 매일 쌓는 macro_history(개요 매크로 칸과 같은 출처). 지난 브리핑도 그 주까지만 그린다.
function MacroWeek({ macro, hist, week }: { macro: NonNullable<Briefing["macro"]>; hist: Record<string, Point[]>; week: string }) {
  const [open, setOpen] = useState<MacroKey | null>(null);
  const { start, end } = weekWindow(week);
  const rows = MACRO_ROWS.filter((r) => macro[r.key]?.value != null);
  const cur = rows.find((r) => r.key === open);
  const hasLines = rows.some((r) => (hist[r.key] ?? []).length > 1);
  return (
    <div className="mt-1.5">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
        {rows.map((r) => {
          const m = macro[r.key]!;
          const chg = r.chg ?? usdChg(m);
          const on = open === r.key;
          return (
            <button key={r.key} type="button" onClick={() => setOpen(on ? null : r.key)} aria-expanded={on}
              className="rounded-lg px-2.5 py-1.5 text-left"
              style={{ background: "var(--bg-inset)", border: `1px solid ${on ? "var(--border-ctrl)" : "var(--border)"}` }}>
              <p className="text-[12px] truncate" style={{ color: "var(--text-muted)" }}>{r.label}</p>
              <p className="flex flex-wrap items-baseline gap-x-1.5" style={{ fontVariantNumeric: "tabular-nums" }}>
                <span className="text-[13px] font-bold text-white">{r.fmt(m.value!)}</span>
                {m.chg_1w != null && <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>주간 {chg(m.chg_1w)}</span>}
              </p>
              <div className="mt-1"><WeekSpark points={hist[r.key] ?? []} week={week} /></div>
            </button>
          );
        })}
      </div>
      {cur && (
        <div className="mt-1.5 rounded-lg p-3" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
          <BigChart key={`${cur.key}-${week}`} points={upTo(hist[cur.key] ?? [], end)} title={cur.label} fmt={cur.fmt} mark={start} initial={22} />
        </div>
      )}
      {hasLines && (
        <p className="text-[11.5px] mt-1" style={{ color: "var(--text-faint)" }}>
          음영이 지난주(직전 거래일 종가부터), 흐린 선은 그 앞 3주 · 누르면 큰 그래프 · 판정 아님
        </p>
      )}
    </div>
  );
}

function StockLabel({ s }: { s: StockRef }) {
  return (
    <StockLink market={s.market} symbol={s.symbol} className="inline-flex items-center gap-1">
      <FlagIcon market={s.market as "US" | "KR"} size={11} />
      <span className="font-bold text-white">{s.market === "KR" ? (s.name && s.name !== s.symbol ? s.name : krStockName(s.symbol)) : s.symbol}</span>
    </StockLink>
  );
}

// 브리핑에서 바로 관찰 노트(2026-10-25) - 🆕 새로 발견·⭐ 관심 종목 줄. 발견 → 재무 확인 → 관찰 시작을 브리핑 안에서.
// 노트는 저장하는 순간의 값을 고정한다 - 지난 주 브리핑에서 열어도 그 주 값이 아니라 오늘 값이라 창에 적어 둔다.
function NoteBtn({ s, past }: { s: { market: string; symbol: string; name?: string | null }; past: boolean }) {
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  const title = s.market === "KR" ? `${s.name || s.symbol} (${s.symbol})` : `${s.symbol}${s.name ? ` · ${s.name}` : ""}`;
  return (
    <>
      <button onClick={() => setOpen(true)} className="text-[11px] px-1.5 rounded hover:brightness-125 whitespace-nowrap"
        style={{ color: saved ? "#4ade80" : "var(--text-muted)", border: `1px solid ${saved ? "#4ade8055" : "var(--border)"}` }}
        title="관찰 노트 남기기 - 4주·12주 뒤 그때와 지금을 대조">
        {saved ? "✓ 노트" : "✎ 노트"}
      </button>
      {open && (
        <ObservationForm kind="stock" market={s.market as "US" | "KR"} ticker={s.symbol} title={title}
          notice={past ? "지난 주 브리핑에서 열었지만, 노트에는 지금(오늘) 값이 기록됩니다." : undefined}
          onClose={() => setOpen(false)} onSaved={() => setSaved(true)} />
      )}
    </>
  );
}

// 지수 1주 변화 - 두 칸 나란히(2026-10-21 브리핑 레이아웃 정리)
function IndexTile({ label, m }: { label: string; m: MarketWeek }) {
  const v = m?.index_chg_1w;
  return (
    <div className="rounded-lg px-3 py-2" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
      <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>{label}</p>
      <p className="text-[16px] font-bold" style={{ color: v == null ? "var(--text-faint)" : v >= 0 ? "#4ade80" : "#f87171", fontVariantNumeric: "tabular-nums" }}>
        {v == null ? "—" : `${v >= 0 ? "+" : ""}${v}%`}
      </p>
    </div>
  );
}

// 브리핑 레이아웃(2026-10-21) - 예전엔 칸 제목이 회색 12px 한 줄이라 어디서 칸이 바뀌는지 안 보였다.
// 칸마다 카드 하나 + 제목·건수 한 줄로, 비슷한 칸끼리 묶음 제목 아래 둔다. 2026-10-25부터 공용 Section·GroupTitle(src/components/Section.tsx).
// 스크롤 여백: 위에 붙는 주 선택 띠 높이(휴대폰은 목차 줄까지)만큼
const SCROLL_M = "scroll-mt-28 lg:scroll-mt-20";
function Sub({ children }: { children: ReactNode }) {
  return <p className="text-[12px] font-semibold mt-3 first:mt-0 mb-1" style={{ color: "var(--text-secondary)" }}>{children}</p>;
}
// 공시·내부자 목록(2026-11-02, 사용자 요청: 공시가 난잡하다 - 중요한 것만). 줄마다 상자를 두르던 것을 한 상자 안의 줄 목록으로,
// isKey에 걸리는 줄(관심 종목·해지·큰 계약·흑자/적자 전환 등)만 먼저 보이고 나머지는 "나머지 N건"으로 접는다. 걸리는 줄이 없으면 앞 minShow줄.
// 순위·점수가 아니라 정해 둔 조건에 맞는지일 뿐(원칙 1) - 접힌 줄도 펼치면 그대로 다 보인다.
function Rows<T>({ items, isKey, render, minShow = 3, restLabel = "나머지" }: {
  items: T[]; isKey: (x: T) => boolean; render: (x: T) => ReactNode; minShow?: number; restLabel?: string;
}) {
  const [all, setAll] = useState(false);
  const keys = items.filter(isKey);
  const base = keys.length > 0 ? keys : items.slice(0, minShow);
  const ordered = keys.length > 0 ? [...keys, ...items.filter((x) => !isKey(x))] : items;
  const list = all ? ordered : base;
  const rest = items.length - base.length;
  if (items.length === 0) return null;
  return (
    <>
      <div className="rounded-lg overflow-hidden" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
        {list.map((x, i) => <div key={i} style={i ? { borderTop: "1px solid var(--border)" } : undefined}>{render(x)}</div>)}
      </div>
      {rest > 0 && (
        <button onClick={() => setAll(!all)} className="mt-1 text-[12px] hover:underline" style={{ color: "#ffb020" }}>
          {all ? "접기" : `${restLabel} ${rest}건 보기`}
        </button>
      )}
    </>
  );
}
// 8-K 핵심(2026-11-02): 주의 종류이거나, 임원 변동(5.02)·주총 결과(5.07)·공정공시(7.01)·기타(8.01)가 아닌 항목이 있는 것
const MINOR_8K = new Set(["5.02", "5.07", "7.01", "8.01", "9.01"]);
const key8k = (x: Us8kItem) => x.warn || x.items.some((i) => !MINOR_8K.has(i.item));
function Us8kRow({ x }: { x: Us8kItem }) {
  const [open, setOpen] = useState(false);
  const ex = x.items.find((i) => i.excerpt)?.excerpt;
  return (
    <div style={rowMark(false, x.warn)}>
      <div className={ROW}>
        <span className="w-11 shrink-0 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>{dayLabel(x.date)}</span>
        <StockLink market="US" symbol={x.symbol} className="font-bold text-white">{x.symbol}</StockLink>
        {x.url && <a href={x.url} target="_blank" rel="noreferrer" title="SEC 공시 원문" className="text-[11px] hover:underline" style={{ color: "var(--text-faint)" }}>↗</a>}
        {x.items.map((i) => <span key={i.item} style={{ color: i.warn ? "#f87171" : "var(--text-secondary)" }}>{i.label}</span>)}
        <DiscTags tags={x.tags} />
        {ex && (
          <button onClick={() => setOpen(!open)} className="ml-auto text-[11px] hover:underline" style={{ color: "var(--text-muted)" }} aria-expanded={open}>
            {open ? "▾ 접기" : "▸ 원문 첫머리"}
          </button>
        )}
      </div>
      {open && ex && <p className="px-3 pb-2 -mt-0.5 text-[12px]" style={{ color: "var(--text-muted)" }}>{ex}</p>}
    </div>
  );
}

// 줄 강조: 관심 종목은 왼쪽 노란 띠, 주의(해지·구조조정 등)는 붉은 띠 - 상자 테두리 대신
const rowMark = (tagged: boolean, warn = false): CSSProperties =>
  tagged ? { background: "#f59e0b0d", boxShadow: "inset 3px 0 0 #f59e0b" } : warn ? { background: "#f871710a", boxShadow: "inset 3px 0 0 #f87171" } : {};
const ROW = "flex items-center gap-x-2 gap-y-0.5 flex-wrap text-[12px] px-3 py-1.5";
const dayLabel = (d?: string | null) => (d ? d.slice(5).replace("-", "/") : "-");

const byMarket = (m: Record<string, number>, unit = "") =>
  Object.entries(m).sort(([a], [c]) => c.localeCompare(a)).map(([k, n]) => `${k === "KR" ? "한국" : "미국"} ${n}${unit}`).join(" · ");

type TocItem = { id: string; label: string; count?: string; group: string };

// 브리핑 묶음 머리(2026-11-02, 사용자 요청: 종목 변화·테마를 먼저, 묶음이 구분되게) - 회색 작은 제목 대신 색 띠.
// 색은 묶음 구분용일 뿐 좋고 나쁨이 아니다. 안에 보여 줄 칸이 없으면 머리도 숨긴다(GroupTitle과 같은 규칙).
const GROUP_META: Record<string, { emoji: string; color: string; desc: string }> = {
  "종목 변화": { emoji: "🔖", color: "#ffb020", desc: "워치리스트에 들어오고 나간 종목, 실적 반전, 관심도" },
  "테마": { emoji: "📡", color: "#6fb3b8", desc: "테마 레이더 라벨이 새로 붙거나 사라진 테마" },
  "시장": { emoji: "🌐", color: "#a78bfa", desc: "지수·수급·금리·환율 등 지난주 시장 배경" },
  "이번 주 일정": { emoji: "📅", color: "#60a5fa", desc: "이번 주 실적을 발표하는 종목" },
  "공시 · 내부자": { emoji: "📄", color: "#fb923c", desc: "지난 7일 공시·내부자 매수·13F - 중요한 줄만 먼저" },
};
function BriefGroup({ title, children }: { title: string; children: ReactNode }) {
  const kids = Children.toArray(children);
  if (kids.length === 0) return null;
  const m = GROUP_META[title];
  return (
    <div className="space-y-2">
      <div className="mt-3 rounded-lg px-3 py-2" style={{ background: (m?.color ?? "#888") + "10", borderLeft: `4px solid ${m?.color ?? "var(--border-ctrl)"}` }}>
        <p className="text-[15px] font-extrabold" style={{ color: m?.color ?? "var(--text-primary)" }}>{m?.emoji} {title}</p>
        {m?.desc && <p className="text-[12px]" style={{ color: "var(--text-secondary)" }}>{m.desc}</p>}
      </div>
      {kids}
    </div>
  );
}

// 주간 총평 본문(2026-11-02) - "■ 소제목" 줄은 제목으로, 나머지는 문단. 접힌 상태에선 앞 두 묶음만(예전 형식 - 소제목 없는 글은 4줄).
type NewsItem = { title: string; url: string; source: string; published_at: string };

function NewsLinks({ items }: { items: NewsItem[] }) {
  return (
    <ul className="mt-1 space-y-0.5">
      {items.map((n) => (
        <li key={n.url} className="text-[11.5px] leading-snug flex gap-1.5 min-w-0">
          <span className="shrink-0" style={{ color: "#6f6857" }}>📰</span>
          <a href={n.url} target="_blank" rel="noopener noreferrer" className="hover:underline min-w-0" style={{ color: "#a9a18c" }}>
            {n.title}
            <span className="ml-1.5 whitespace-nowrap" style={{ color: "#6f6857" }}>
              {[n.source, n.published_at ? n.published_at.slice(5).replace("-", "/") : ""].filter(Boolean).join(" · ")}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

function CommentBody({ text, collapsed, news }: { text: string; collapsed: boolean; news?: Record<string, NewsItem[]> }) {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  if (!lines.some((l) => l.startsWith("■"))) {
    return <p className={`text-[14px] leading-relaxed whitespace-pre-line ${collapsed ? "line-clamp-4" : ""}`} style={{ color: "var(--text-body, #d6d0c0)" }}>{text}</p>;
  }
  const blocks: { head: string; body: string[] }[] = [];
  for (const l of lines) {
    if (l.startsWith("■")) blocks.push({ head: l.replace(/^■\s*/, ""), body: [] });
    else if (blocks.length) blocks[blocks.length - 1].body.push(l);
    else blocks.push({ head: "", body: [l] });
  }
  return (
    <div className="space-y-4">
      {(collapsed ? blocks.slice(0, 2) : blocks).map((blk, i) => {
        // 소제목 "이름 · 종류"(2026-11-02 짚을 점) - 종류는 작은 꼬리표로
        const [name, ...tags] = blk.head.split(" · ");
        return (
          <div key={i}>
            {blk.head && (
              <p className="h-sub mb-1 flex flex-wrap items-center gap-1.5" style={{ color: "#ffb020", fontSize: 15.5 }}>
                <span>{name}</span>
                {tags.map((t) => (
                  <span key={t} className="text-[11.5px] font-medium px-1.5 py-[1px] rounded border whitespace-nowrap"
                        style={{ color: t.includes("엇갈림") || t.includes("주의") ? "#ff8a7a" : "#c9b98a", borderColor: "#3a3426" }}>{t}</span>
                ))}
              </p>
            )}
            {blk.body.map((t, k) => t.startsWith("→") ? (
              <p key={k} className="text-[13px] leading-relaxed mt-1" style={{ color: "#7fb8a4" }}>
                {t}
              </p>
            ) : <p key={k} className="text-[14.5px] leading-[1.75]" style={{ color: "#d6d0c0" }}>{t}</p>)}
            {!collapsed && news?.[blk.head]?.length ? <NewsLinks items={news[blk.head]} /> : null}
          </div>
        );
      })}
    </div>
  );
}

function BriefingView({ b, picker, past, macroHist }: { b: Briefing; picker: ReactNode; past: boolean; macroHist: Record<string, Point[]> }) {
  const wl = b.watchlist ?? { total: 0, added: [], removed: [], top: [], has_prev: false };
  const [active, setActive] = useState("");
  const [commentOpen, setCommentOpen] = useState(false);
  const chipsRef = useRef<HTMLDivElement>(null);

  const has = {
    mine: (b.my_stocks_week?.count ?? 0) > 0,
    comment: !!b.gpt_comment,
    labels: !!b.theme_labels && (b.theme_labels.new_labels.length > 0 || b.theme_labels.dropped_labels.length > 0),
    earnings: (b.earnings_week?.total ?? 0) > 0,
    disclosures: !!b.kr_disclosures && discTotal(b) > 0,
    us8k: (b.us_8k_week?.total ?? 0) > 0,
    insider: (b.insider_week?.total ?? 0) > 0,
    inst13f: (b.inst_13f_week?.filers ?? 0) > 0,
    turnaround: !!b.turnaround,
    sentiment: (b.sentiment_heating?.length ?? 0) > 0,
  };
  // 목차 - 아래 칸 순서 그대로. 앵커는 개요 "이번 주 변화"·⭐ 줄이 쓰는 짧은 이름(#earnings 등)
  const toc: TocItem[] = [
    ...(has.mine ? [{ id: "mine", label: "⭐ 관심 종목", count: `${b.my_stocks_week!.count}`, group: "" }] : []),
    ...(has.comment ? [{ id: "comment", label: "총평", group: "" }] : []),
    { id: "market", label: "지난주 시장", group: "시장" },
    { id: "watchlist", label: "워치리스트",
      count: wl.has_prev ? `+${wl.added_count ?? wl.added.length} −${wl.removed_count ?? wl.removed.length}` : undefined, group: "종목 변화" },
    ...(has.turnaround ? [{ id: "turnaround", label: "실적 반전", count: b.turnaround!.has_prev ? `+${b.turnaround!.added_count}` : undefined, group: "종목 변화" }] : []),
    ...(has.sentiment ? [{ id: "sentiment", label: "관심도", count: `${b.sentiment_heating.length}`, group: "종목 변화" }] : []),
    ...(has.labels ? [{ id: "labels", label: "테마 라벨",
      count: `${b.theme_labels!.new_labels.length + b.theme_labels!.dropped_labels.length}`, group: "테마" }] : []),
    ...(has.earnings ? [{ id: "earnings", label: "실적 발표", count: `${b.earnings_week!.total}`, group: "이번 주 일정" }] : []),
    ...(has.disclosures ? [{ id: "disclosures", label: "한국 공시", count: `${discTotal(b)}`, group: "공시 · 내부자" }] : []),
    ...(has.us8k ? [{ id: "us8k", label: "미국 8-K", count: `${b.us_8k_week!.total}`, group: "공시 · 내부자" }] : []),
    ...(has.insider ? [{ id: "insider", label: "내부자 매수", count: `${b.insider_week!.total}`, group: "공시 · 내부자" }] : []),
    ...(has.inst13f ? [{ id: "inst13f", label: "13F", count: `${b.inst_13f_week!.filers}곳`, group: "공시 · 내부자" }] : []),
  ];
  const tocKey = toc.map((t) => t.id).join();

  // 지금 읽는 칸을 목차에 표시 - 본문은 <main> 안에서 스크롤된다
  useEffect(() => {
    const main = document.querySelector("main");
    if (!main) return;
    const ids = tocKey.split(",");
    const onScroll = () => {
      let cur = ids[0];
      for (const id of ids) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top < 160) cur = id;
      }
      setActive(cur);
    };
    onScroll();
    main.addEventListener("scroll", onScroll, { passive: true });
    return () => main.removeEventListener("scroll", onScroll);
  }, [tocKey]);
  // 휴대폰 목차 줄은 가로로 넘치니 지금 칸이 보이게 옆으로 민다
  useEffect(() => {
    const c = chipsRef.current;
    const el = c?.querySelector<HTMLElement>(`[data-id="${active}"]`);
    if (c && el) c.scrollTo({ left: Math.max(0, el.offsetLeft - 24), behavior: "smooth" });
  }, [active]);

  const chip = (t: TocItem) => {
    const on = t.id === active;
    return (
      <a key={t.id} data-id={t.id} href={`#${t.id}`} className="shrink-0 whitespace-nowrap text-[12px] px-2.5 py-1 rounded-full"
        style={{ background: on ? "#ffb02022" : "var(--bg-inset)", border: `1px solid ${on ? "#ffb02066" : "var(--border)"}`, color: on ? "#ffb020" : "var(--text-secondary)" }}>
        {t.label}{t.count && <span className="ml-1" style={{ color: on ? "#ffb020" : "var(--text-muted)" }}>{t.count}</span>}
      </a>
    );
  };
  const groups = Array.from(new Set(toc.map((t) => t.group)));
  const longComment = (b.gpt_comment ?? "").length > 260;

  return (
    <>
      {/* 주 선택 + (휴대폰) 목차 - 스크롤해도 위에 붙어 있다. <main>의 위 여백(pt-8)만큼 올려야 맨 위에 붙는다 */}
      <div className="sticky -top-8 z-20 -mx-4 px-4 md:-mx-7 md:px-7 py-2" style={{ background: "var(--bg-base)", borderBottom: "1px solid var(--border)" }}>
        {picker}
        <div ref={chipsRef} className="lg:hidden relative mt-2 flex gap-1.5 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
          {toc.map(chip)}
        </div>
      </div>

      <div className="mt-3 lg:grid lg:grid-cols-[minmax(0,1fr)_11rem] lg:gap-5">
        <div className="space-y-2 min-w-0">
          {has.mine && (
            <Section className={SCROLL_M} id="mine" tone="mine" title="⭐ 관심 종목에 생긴 일"
              sub={`내 관심·노트 ${b.my_stocks_week!.watched}종목 중 ${b.my_stocks_week!.count}종목`}>
              <div className="divide-y" style={{ borderColor: "#f59e0b22" }}>
                {b.my_stocks_week!.items.map((x) => (
                  <div key={`${x.market}:${x.symbol}`} className="py-1.5 first:pt-0 last:pb-0" style={{ borderColor: "#f59e0b22" }}>
                    <div className="flex flex-wrap items-center gap-1.5 text-[13px]">
                      <StockLabel s={x} /><DiscTags tags={x.tags} /><NoteBtn s={x} past={past} />
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {x.events.map((e, i) => (
                        <a key={i} href={e.anchor === "notes" ? "/notes" : `#${e.anchor}`} className="text-[12px] px-2 py-0.5 rounded hover:brightness-125"
                          style={e.warn ? { background: "#f8717114", border: "1px solid #f8717144", color: "#fca5a5" }
                            : { background: "var(--bg-inset)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                          <span style={{ color: e.warn ? "#f87171" : "var(--text-muted)" }}>{e.kind}</span> {e.text}
                        </a>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              <Note>아래 항목(실적 발표·한국 공시·미국 8-K·내부자 매수·실적 반전)과 노트 회고에서 내 관심·노트 종목만 모았습니다 · 누르면 해당 항목으로</Note>
            </Section>
          )}

          {has.comment && (
            <Section className={SCROLL_M} id="comment" tone="warm" title="주간 총평">
              <CommentBody text={b.gpt_comment} collapsed={longComment && !commentOpen} news={b.comment_news} />
              {longComment && (
                <button onClick={() => setCommentOpen(!commentOpen)} className="mt-1 text-[12px] hover:underline" style={{ color: "#ffb020" }}>
                  {commentOpen ? "접기" : "전체 보기"}
                </button>
              )}
            </Section>
          )}

          <BriefGroup title="시장">
            <Section className={SCROLL_M} id="market" title="지난주 시장">
              {b.regime && <RegimeBadges regime={b.regime} />}
              <div className="grid grid-cols-2 gap-1.5">
                <IndexTile label="🇺🇸 S&P 500 주간" m={b.us} />
                <IndexTile label="🇰🇷 KOSPI 주간" m={b.kr} />
              </div>
              {b.kr_flows && (
                <div className="mt-1.5 space-y-1.5">
                  <FlowRow label="코스피 수급" f={b.kr_flows.KOSPI} />
                  <FlowRow label="코스닥 수급" f={b.kr_flows.KOSDAQ} />
                </div>
              )}
              {b.macro && <MacroWeek macro={b.macro} hist={macroHist} week={b.week} />}
            </Section>
          </BriefGroup>

          <BriefGroup title="종목 변화">
            <Section className={SCROLL_M} id="watchlist" title="워치리스트 변동" sub={`후보 ${wl.total}개`}>
              {!wl.has_prev ? (
                <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>첫 기록 주입니다 — 다음 주부터 신규·탈락을 비교합니다.</p>
              ) : wl.added.length === 0 && wl.removed.length === 0 ? (
                <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>변동 없음</p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <div className="rounded-lg p-2.5" style={{ background: "var(--bg-inset)", border: "1px solid #ffb02022" }}>
                    <p className="text-[12px] font-bold mb-1.5" style={{ color: "#ffb020" }}>+ 신규 진입 ({wl.added_count ?? wl.added.length})</p>
                    <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12px]">
                      {wl.added.map((s) => (
                        <span key={`${s.market}:${s.symbol}`}>
                          <StockLabel s={s} />
                          {s.fit_score != null && <span className="ml-1" style={{ color: "var(--text-muted)" }}>적합 {s.fit_score}</span>}
                        </span>
                      ))}
                    </div>
                    {wl.added.length === 0 && <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>없음</p>}
                    {(wl.added_count ?? 0) > wl.added.length && <p className="text-[12px] mt-1" style={{ color: "var(--text-muted)" }}>외 {(wl.added_count ?? 0) - wl.added.length}개 - 워치리스트 &quot;이번 회차 신규만&quot;에서 전체 보기</p>}
                  </div>
                  <div className="rounded-lg p-2.5" style={{ background: "var(--bg-inset)", border: "1px solid #f8717122" }}>
                    <p className="text-[12px] font-bold mb-1.5" style={{ color: "#f87171" }}>− 탈락 ({wl.removed_count ?? wl.removed.length})</p>
                    <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12px]">
                      {wl.removed.map((s) => <span key={`${s.market}:${s.symbol}`}><StockLabel s={s} /></span>)}
                    </div>
                    {wl.removed.length === 0 && <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>없음</p>}
                    {(wl.removed_count ?? 0) > wl.removed.length && <p className="text-[12px] mt-1" style={{ color: "var(--text-muted)" }}>외 {(wl.removed_count ?? 0) - wl.removed.length}개</p>}
                  </div>
                </div>
              )}
            </Section>

            {has.turnaround && (
              <Section className={SCROLL_M} id="turnaround" title="실적 반전"
                sub={`${byMarket(b.turnaround!.by_market) || "0"}${b.turnaround!.has_prev ? ` · 신규 ${b.turnaround!.added_count} · 빠짐 ${b.turnaround!.removed_count}` : ""}`}>
                {b.turnaround!.added.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {b.turnaround!.added.map((s) => (
                      <span key={`${s.market}:${s.symbol}`} className="text-[12px] px-2 py-1 rounded-lg"
                        style={{ background: "#4ade8012", border: "1px solid #4ade8033" }}>
                        <StockLabel s={s} />
                        {s.yoy != null && <span style={{ color: "#4ade80" }}> {s.basis} {s.yoy >= 0 ? "+" : ""}{(s.yoy * 100).toFixed(0)}%</span>}
                      </span>
                    ))}
                    {b.turnaround!.added_count > b.turnaround!.added.length && (
                      <span className="text-[12px] self-center" style={{ color: "var(--text-muted)" }}>외 {b.turnaround!.added_count - b.turnaround!.added.length}개</span>
                    )}
                  </div>
                ) : (
                  <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>
                    {b.turnaround!.has_prev ? "이번 주 새로 들어온 종목 없음" : "새로 들어온 종목 비교는 다음 주부터"}
                  </p>
                )}
                <Note label="조건">매출 3년은 정체·역성장인데 최근 1년(4개 분기 합, 없으면 최근 분기)은 성장 — 워치리스트 &quot;실적 반전&quot; 버튼과 같은 조건</Note>
              </Section>
            )}

            {has.sentiment && (
              <Section className={SCROLL_M} id="sentiment" title="관심도 상승" count={b.sentiment_heating.length}>
                <div className="flex flex-wrap gap-1.5">
                  {b.sentiment_heating.map((s) => (
                    <span key={`${s.market}:${s.symbol}`} className="text-[12px] px-2 py-1 rounded-lg"
                      style={{ background: "#f8717112", border: "1px solid #f8717133" }}>
                      <StockLabel s={s} /> <span style={{ color: "#f87171" }}>{s.path}</span>
                    </span>
                  ))}
                </div>
              </Section>
            )}
          </BriefGroup>

          {/* 테마 레이더 라벨 변동 — 라벨 계산은 별도 워크플로우라 이 브리핑보다 늦게
              끝날 수 있어서, "이번 주"라 단정하지 않고 실제 기준 주를 그대로 보여준다. */}
          <BriefGroup title="테마">
            {has.labels && (
              <Section className={SCROLL_M} id="labels" title="📡 테마 레이더 라벨 변동" sub={`${b.theme_labels!.week_start} 기준`}>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {b.theme_labels!.new_labels.length > 0 && (
                    <div className="rounded-lg p-2.5" style={{ background: "var(--bg-inset)", border: "1px solid #ffb02022" }}>
                      <p className="text-[12px] font-bold mb-1" style={{ color: "#ffb020" }}>+ 신규 라벨 ({b.theme_labels!.new_labels.length})</p>
                      {b.theme_labels!.new_labels.map((t) => (
                        <p key={`${t.market ?? "US"}:${t.theme_id}`} className="text-[12px] py-0.5">
                          <span className="mr-1">{t.market === "KR" ? "🇰🇷" : "🇺🇸"}</span>
                          <span className="font-bold text-white">{themeName(t.theme_id).ko}</span>
                          <span className="ml-1.5" style={{ color: "var(--text-muted)" }}>{labelWithKo(t.label)}</span>
                        </p>
                      ))}
                    </div>
                  )}
                  {b.theme_labels!.dropped_labels.length > 0 && (
                    <div className="rounded-lg p-2.5" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                      <p className="text-[12px] font-bold mb-1" style={{ color: "var(--text-faint)" }}>− 소멸 라벨 ({b.theme_labels!.dropped_labels.length})</p>
                      {b.theme_labels!.dropped_labels.map((t) => (
                        <p key={`${t.market ?? "US"}:${t.theme_id}`} className="text-[12px] py-0.5" style={{ color: "var(--text-faint)" }}>
                          {t.market === "KR" ? "🇰🇷" : "🇺🇸"} {themeName(t.theme_id).ko} <span>({labelWithKo(t.label)})</span>
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              </Section>
            )}
          </BriefGroup>

          <BriefGroup title="이번 주 일정">
            {has.earnings && (
              <Section className={SCROLL_M} id="earnings" title="실적 발표" count={b.earnings_week!.total} sub={byMarket(b.earnings_week!.by_market)}>
                <div className="space-y-1.5">
                  {Array.from(new Set(b.earnings_week!.items.map((x) => x.date))).map((d) => (
                    <div key={d} className="flex items-start gap-2">
                      <span className="text-[12px] font-bold text-white w-16 shrink-0 pt-1 whitespace-nowrap">{mdw(d)}</span>
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
                <Note>워치리스트 후보·내 관심·관찰 노트 종목 · 날짜는 yfinance(회사 공지 전이면 &quot;예상&quot;), 한국은 결산실적 공시예고가 있으면 그 날짜 · 노란색은 내 관심·노트·실적 반전 종목</Note>
              </Section>
            )}
          </BriefGroup>

          <BriefGroup title="공시 · 내부자">
            {has.disclosures && (() => {
              const k = b.kr_disclosures!;
              const fix = [...(k.termination?.items ?? []), ...(k.amend?.items ?? [])];
              // 핵심 조건(2026-11-02): 관심 종목은 늘, 계약은 매출 대비 10% 이상, 잠정실적은 흑자·적자 전환
              const keyContract = (d: DisclosureItem) => d.tags.length > 0 || (d.pct ?? 0) >= 10;
              const keyPrelim = (d: DisclosureItem) => d.tags.length > 0 || !!d.operating_income_yoy_turn || !!d.revenue_yoy_turn;
              return (
                <Section className={SCROLL_M} id="disclosures" title="🇰🇷 한국 공시" count={discTotal(b)}
                  sub={[`지난 7일`, `공급계약 ${k.contract.count}`, `잠정실적 ${k.prelim.count}`,
                    ...((k.termination?.count ?? 0) > 0 ? [`해지 ${k.termination!.count}`] : []),
                    ...((k.amend?.count ?? 0) > 0 ? [`정정 ${k.amend!.count}`] : [])].join(" · ")}>
                  {fix.length > 0 && (
                    <>
                      <Sub>⚠️ 계약 해지 · 금액 정정</Sub>
                      <Rows items={fix} isKey={() => true} render={(d) => (
                        <div className={ROW} style={rowMark(d.tags.length > 0, true)}>
                          <span className="w-11 shrink-0 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>{dayLabel(d.date)}</span>
                          <DiscName d={d} />
                          <span style={{ color: "#fca5a5" }}>{d.summary}</span>
                          <DiscTags tags={d.tags} />
                        </div>
                      )} />
                    </>
                  )}
                  {k.contract.items.length > 0 && (
                    <>
                      <Sub>공급계약 <span className="font-normal" style={{ color: "var(--text-muted)" }}>관심 종목 · 매출 대비 10% 이상 먼저</span></Sub>
                      <Rows items={k.contract.items} isKey={keyContract} render={(d) => (
                        <div className={ROW} style={rowMark(d.tags.length > 0)}>
                          <span className="w-11 shrink-0 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>{dayLabel(d.date)}</span>
                          <DiscName d={d} />
                          <span className="font-semibold text-white">{d.withheld ? "금액 비공개" : eok(d.amount)}</span>
                          {d.pct != null && <span style={{ color: d.pct >= 10 ? "#4ade80" : "var(--text-muted)" }}>매출의 {d.pct.toFixed(1)}%</span>}
                          {d.title && <span className="truncate max-w-[14rem]" style={{ color: "var(--text-muted)" }}>{d.title}</span>}
                          <DiscTags tags={d.tags} />
                        </div>
                      )} />
                    </>
                  )}
                  {k.prelim.items.length > 0 && (
                    <>
                      <Sub>잠정실적 <span className="font-normal" style={{ color: "var(--text-muted)" }}>관심 종목 · 흑자·적자 전환 먼저 · 전년 같은 분기 대비</span></Sub>
                      <Rows items={k.prelim.items} isKey={keyPrelim} render={(d) => (
                        <div className={ROW} style={rowMark(d.tags.length > 0)}>
                          <span className="w-11 shrink-0 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>{dayLabel(d.date)}</span>
                          <DiscName d={d} />
                          {d.quarter && <span style={{ color: "var(--text-faint)" }}>{d.quarter}</span>}
                          <YoY label="매출" pct={d.revenue_yoy_pct} turn={d.revenue_yoy_turn} />
                          <YoY label="영업익" pct={d.operating_income_yoy_pct} turn={d.operating_income_yoy_turn} />
                          <DiscTags tags={d.tags} />
                        </div>
                      )} />
                    </>
                  )}
                  <Note>먼저 보이는 줄: 관심 종목(내 관심·노트·워치리스트·테마), 계약 해지·금액 정정, 매출 대비 10% 이상 공급계약, 흑자·적자 전환 잠정실적 -
                    나머지는 접어 둠(순위 아님) · 대상: 시총 3000억 이상 또는 관심 종목, 날짜만 바뀐 정정·자회사 공시 제외 · 목록은 종류별 30건까지 ·
                    이름은 종목 상세, ↗는 DART 원문</Note>
                </Section>
              );
            })()}

            {has.us8k && (
              <Section className={SCROLL_M} id="us8k" title="🇺🇸 미국 8-K" count={b.us_8k_week!.total}
                sub={`지난 7일 · ${Object.entries(b.us_8k_week!.by_kind).map(([k, n]) => `${k} ${n}`).join(" · ")}`}>
                <Rows items={b.us_8k_week!.items} isKey={key8k} restLabel="임원 변동 등 나머지" render={(x) => <Us8kRow x={x} />} />
                {b.us_8k_week!.total > b.us_8k_week!.items.length && (
                  <p className="text-[12px] mt-1" style={{ color: "var(--text-muted)" }}>목록은 {b.us_8k_week!.items.length}건까지</p>
                )}
                <Note>관심 종목(워치리스트·내 관심·노트·테마)의 8-K · 먼저 보이는 줄: 주의 종류(계약 해지·구조조정·손상·감사인 교체 등, 붉은 띠)와
                  중요 계약·인수·상장 관련 - 임원 변동·주총 결과·기타 공시는 접어 둠 · 실적 발표만 있는 8-K는 뺌 · ▸를 누르면 원문 첫머리(번역·요약 없음)</Note>
              </Section>
            )}

            {has.insider && (() => {
              const ins = b.insider_week!;
              return (
                <Section className={SCROLL_M} id="insider" title="내부자 장내 매수" count={ins.total} sub={`지난 7일 공시 · ${byMarket(ins.by_market, "종목")}`}>
                  {ins.discovery ? (
                    <>
                      {ins.items.length > 0 && (
                        <>
                          <Sub>관심 종목 {ins.tagged_count ?? ins.items.length}</Sub>
                          <Rows items={ins.items} isKey={() => true} render={(x) => <InsiderRow x={x} />} />
                        </>
                      )}
                      {ins.discovery.length > 0 && (
                        <>
                          <Sub>🆕 새로 발견(관심 외) {ins.discovery_count ?? ins.discovery.length}{" "}
                            <span className="font-normal" style={{ color: "var(--text-muted)" }}>여러 명이 함께 산 종목 먼저 · 매수자 수 → 금액 순</span></Sub>
                          <Rows items={ins.discovery} isKey={(x) => x.buyers > 1 && !x.all_plan} minShow={5} restLabel="1명 매수·계획 매수 등 나머지"
                            render={(x) => <InsiderRow x={x} showFinance note={<NoteBtn s={x} past={past} />} />} />
                        </>
                      )}
                    </>
                  ) : (
                    <Rows items={ins.items} isKey={() => true} render={(x) => <InsiderRow x={x} />} />
                  )}
                  <Note>임원·이사·대주주가 장내에서 직접 산 것만(스톡옵션·증여·장외 제외) · 금액은 공시 단가 × 주식 수 합계 · 목록은 각 30종목까지
                    {ins.discovery && " · 관심 외는 미국 S&P 500·400, 한국 시총 3000억+ 중 관심 표시가 없는 종목, 재무 판정은 재무 필터 기준(통과·탈락·데이터 부족)"}</Note>
                </Section>
              );
            })()}

            {has.inst13f && (
              <Section className={SCROLL_M} id="inst13f" title="🏦 유명 투자자 13F" count={`${b.inst_13f_week!.filers}곳`}
                sub="지난 7일 신고 · 분기 말 보유(45일 늦음)" right={<a href="/investors" className="hover:underline" style={{ color: "var(--text-muted)" }}>전체 보기 →</a>}>
                <div className="space-y-3">
                  {b.inst_13f_week!.items.map((it) => (
                    <div key={`${it.manager_id}-${it.period}`}>
                      <p className="text-[13px] mb-1">
                        <span className="font-bold text-white">{it.name}</span>
                        {it.style && STYLE_META[it.style as InvestorStyle] && (
                          <span className="ml-1.5 text-[12px] font-semibold" style={{ color: STYLE_META[it.style as InvestorStyle].color }}>
                            {STYLE_META[it.style as InvestorStyle].emoji} {it.style}</span>
                        )}
                        <span className="ml-1.5 text-[12px]" style={{ color: "var(--text-muted)" }}>
                          {qLabel(it.period)} 말 · {it.filed.slice(5).replace("-", "/")} 신고
                          {it.compared && ` · 신규 ${it.counts.new} · 추가 ${it.counts.added} · 일부 매도 ${it.counts.reduced} · 전량 매도 ${it.counts.sold}`}
                        </span>
                      </p>
                      {!it.compared ? <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>직전 분기 자료가 없어 비교하지 않습니다.</p> : (
                        <div className="space-y-1">
                          {it.new.length > 0 && <div className="flex flex-wrap items-center gap-1.5"><span className="text-[12px] w-14 shrink-0" style={{ color: "#4ade80" }}>신규 매수</span>{it.new.map((x, k) => <InstChip key={k} x={x} />)}</div>}
                          {it.sold.length > 0 && <div className="flex flex-wrap items-center gap-1.5"><span className="text-[12px] w-14 shrink-0" style={{ color: "#fca5a5" }}>전량 매도</span>{it.sold.map((x, k) => <InstChip key={k} x={x} sold />)}</div>}
                          {it.new.length === 0 && it.sold.length === 0 && <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>신규 매수·전량 매도 종목 없음</p>}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                <Note>SEC 13F - 고른 운용사 15곳이 분기 말 들고 있던 미국 상장주식(매수 보유만)을 45일 안에 신고한 것 · 산 시점·가격은 모름 ·
                  평가액은 분기 말 기준, 비중은 그 운용사 주식 보유 중 · 목록은 평가액 순 10개까지 · 노란색은 관심 표시 종목 · 재무 판정은 재무 필터 기준</Note>
              </Section>
            )}
          </BriefGroup>
        </div>

        {/* 넓은 화면 목차 - 묶음별, 지금 읽는 칸 표시 */}
        <aside className="hidden lg:block">
          <nav className="sticky top-12 space-y-3" aria-label="브리핑 목차">
            {groups.map((g) => (
              <div key={g || "top"}>
                {g && <p className="stat-label mb-1" style={GROUP_META[g] ? { color: GROUP_META[g].color } : undefined}>{GROUP_META[g]?.emoji} {g}</p>}
                <div className="space-y-0.5">
                  {toc.filter((t) => t.group === g).map((t) => {
                    const on = t.id === active;
                    return (
                      <a key={t.id} href={`#${t.id}`} className="flex items-baseline gap-1.5 rounded px-2 py-1 text-[13px] hover:brightness-125"
                        style={{ background: on ? "#ffb02014" : undefined, color: on ? "#ffb020" : "var(--text-secondary)",
                          borderLeft: `2px solid ${on ? "#ffb020" : "transparent"}` }}>
                        <span className="truncate">{t.label}</span>
                        {t.count && <span className="ml-auto text-[12px]" style={{ color: on ? "#ffb020" : "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>{t.count}</span>}
                      </a>
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>
        </aside>
      </div>
    </>
  );
}

// 유가·구리·가스 주간 변화: 달러 + (%)
const usdChg = (m?: MacroItem | null) => (v: number) => {
  const base = (m?.value ?? 0) - v;
  const pct = base ? ` (${v / base >= 0 ? "+" : ""}${(v / base * 100).toFixed(1)}%)` : "";
  return `${v >= 0 ? "+" : "-"}$${Math.abs(v).toFixed(2)}${pct}`;
};

// 주 고르기(2026-10-21) - 예전엔 최대 12주 브리핑을 아래로 쌓아 두어(지난 주는 접힌 채) 스크롤이 길었다.
// 한 번에 한 주만 보고 ◀ ▶·목록으로 넘긴다. 지난 주는 주소 ?week=로 남아 공유·새로고침해도 그 주.
function WeekPicker({ weeks, idx, onPick, generatedAt }: { weeks: string[]; idx: number; onPick: (i: number) => void; generatedAt?: string }) {
  const btn = (disabled: boolean) => ({
    background: "var(--bg-inset)", border: "1px solid var(--border)",
    color: disabled ? "var(--text-faint)" : "var(--text-secondary)", opacity: disabled ? 0.5 : 1,
  });
  return (
    <div className="flex items-center gap-1.5">
      <button aria-label="이전 주" disabled={idx >= weeks.length - 1} onClick={() => onPick(idx + 1)}
        className="h-8 w-8 shrink-0 rounded-lg text-[12px]" style={btn(idx >= weeks.length - 1)}>◀</button>
      <select aria-label="브리핑 주 선택" value={idx} onChange={(e) => onPick(Number(e.target.value))}
        className="h-8 min-w-0 rounded-lg px-2 text-[13px] font-bold"
        style={{ background: "var(--bg-inset)", border: "1px solid var(--border)", color: "var(--text-primary)" }}>
        {weeks.map((w, i) => <option key={w} value={i}>📋 {w} 주{i === 0 ? " · 최신" : ` · ${i}주 전`}</option>)}
      </select>
      <button aria-label="다음 주" disabled={idx === 0} onClick={() => onPick(idx - 1)}
        className="h-8 w-8 shrink-0 rounded-lg text-[12px]" style={btn(idx === 0)}>▶</button>
      {idx > 0 && (
        <button onClick={() => onPick(0)} className="h-8 shrink-0 rounded-lg px-2.5 text-[12px]"
          style={{ background: "#ffb02014", border: "1px solid #ffb02044", color: "#ffb020" }}>최신</button>
      )}
      {generatedAt && <span className="ml-auto hidden sm:inline text-[12px] truncate" style={{ color: "var(--text-faint)" }}>{generatedAt} 생성</span>}
    </div>
  );
}

export default function BriefingPage() {
  const [briefings, setBriefings] = useState<Briefing[]>([]);
  const [loading, setLoading] = useState(true);
  const [idx, setIdx] = useState(0);
  const [macroHist, setMacroHist] = useState<Record<string, Point[]>>({});   // 매크로 칸 주간 선(2026-11-02)

  useEffect(() => {
    fetch("/api/data/macro/history")
      .then((r) => r.json())
      .then((d) => setMacroHist(d && typeof d === "object" && !Array.isArray(d) ? d : {}))
      .catch(() => setMacroHist({}));
    fetch("/api/briefing")
      .then((r) => r.json())
      .then((d) => {
        const list: Briefing[] = Array.isArray(d?.briefings) ? d.briefings : [];
        setBriefings(list);
        const w = new URLSearchParams(window.location.search).get("week");
        const i = w ? list.findIndex((x) => x.week === w) : -1;
        if (i > 0) setIdx(i);
      })
      .catch(() => setBriefings([]))
      .finally(() => setLoading(false));
  }, []);

  // 개요 "이번 주 변화"에서 #earnings 등으로 들어오면, 브리핑을 불러온 뒤에야 그 칸이 생긴다 - 그때 스크롤한다.
  useEffect(() => {
    if (loading || !window.location.hash) return;
    const el = document.getElementById(decodeURIComponent(window.location.hash.slice(1)));
    if (el) requestAnimationFrame(() => el.scrollIntoView({ block: "start" }));
  }, [loading]);

  const pick = (i: number) => {
    setIdx(i);
    const w = briefings[i]?.week;
    window.history.replaceState(null, "", i === 0 || !w ? window.location.pathname : `?week=${w}`);
    document.querySelector("main")?.scrollTo({ top: 0 });
  };
  const b = briefings[idx];

  return (
    <div className="max-w-5xl">
      <PageHeader title="주간 브리핑" intro="briefing"
        asOf={!loading && <AsOf date={briefings[0]?.week} cadence="매주 월요일 아침" staleDays={8} />}
        desc="지난주를 돌아보고 이번 주를 준비하는 문서. 한 주씩 봅니다 - 맨 위 ⭐ 관심 종목에 생긴 일부터, 목차를 누르면 해당 항목으로 갑니다." />

      {loading ? (
        <div className="h-24 rounded-xl animate-pulse" style={{ background: "#111009" }} />
      ) : !b ? (
        <EmptyState title="아직 브리핑이 없습니다"
          hint="매주 일요일 밤 워치리스트 스크리닝 뒤 자동으로 만들어집니다. 지금 만들려면 GitHub → Actions → Weekly Watchlist Screen → Run workflow" />
      ) : (
        <BriefingView key={b.week} b={b} past={idx > 0} macroHist={macroHist}
          picker={<WeekPicker weeks={briefings.map((x) => x.week)} idx={idx} onPick={pick} generatedAt={b.generated_at} />} />
      )}
    </div>
  );
}
