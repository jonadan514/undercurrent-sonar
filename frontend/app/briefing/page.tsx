"use client";

import { Children, useEffect, useRef, useState, type ReactNode } from "react";
import FlagIcon from "@/src/components/FlagIcon";
import StockLink from "@/src/components/StockLink";
import { themeName } from "@/src/lib/themeNames";
import { TagBadges } from "@/src/components/TagBadge";
import AsOf from "@/src/components/AsOf";
import { labelWithKo } from "@/src/lib/labelNames";
import PageHeader from "@/src/components/PageHeader";
import Note from "@/src/components/Note";
import EmptyState from "@/src/components/EmptyState";

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
  // tagged_count·discovery(관심 밖 새 이름)는 2026-10-21부터 - 그 전 브리핑은 items 하나에 관심 표시 먼저 섞여 있다
  insider_week?: { total: number; by_market: Record<string, number>; items: InsiderItem[]; tagged_count?: number;
                   discovery?: InsiderItem[]; discovery_count?: number } | null;
  us_8k_week?: { total: number; by_kind: Record<string, number>; items: Us8kItem[] } | null;
  my_stocks_week?: { watched: number; count: number; items: MyStock[] } | null;
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
// 트랩 필터 3분류 - 계산 못 한 것은 탈락이 아니라 데이터부족, 스크리닝 결과가 없으면 미확인(원칙 4)
function FinanceTag({ f }: { f?: InsiderItem["finance"] }) {
  const [label, color] = f?.status === "pass" ? [`재무 통과${f.piotroski != null ? ` F${f.piotroski}` : ""}`, "#4ade80"]
    : f?.status === "fail" ? ["재무 탈락", "#f87171"] : f?.status === "insufficient" ? ["데이터부족", "var(--text-muted)"] : ["재무 미확인", "var(--text-muted)"];
  return <span className="text-[11px] px-1.5 rounded" style={{ color, border: "1px solid var(--border)" }} title={f?.reasons?.join(" / ") || undefined}>{label}</span>;
}
function InsiderRow({ x, showFinance = false }: { x: InsiderItem; showFinance?: boolean }) {
  return (
    <div className="flex items-center gap-2 flex-wrap text-[12px] rounded-lg px-3 py-1.5"
      style={x.tags.length > 0 ? { background: "#f59e0b14", border: "1px solid #f59e0b55" } : { background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
      <span className="w-11 shrink-0 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>{x.last_date ? x.last_date.slice(5).replace("-", "/") : "-"}</span>
      <StockLabel s={x} />
      <span className="text-white">{insiderMoney(x.value, x.market)}</span>
      <span style={{ color: x.buyers > 1 ? "#4ade80" : "var(--text-secondary)" }}>
        {x.buyers > 1 ? `${x.buyers}명` : x.owners[0]}{x.buyers === 1 && x.roles[0] && x.roles[0] !== "-" ? ` (${x.roles[0]})` : ""}
      </span>
      <span style={{ color: "var(--text-muted)" }}>{x.trades}건</span>
      {x.all_plan && <span style={{ color: "var(--text-muted)" }} title="10b5-1: 미리 정해 둔 계획 매수">계획 매수</span>}
      {showFinance && <FinanceTag f={x.finance} />}
      <DiscTags tags={x.tags} />
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
      <p className="text-[12px] truncate" style={{ color: "var(--text-muted)" }}>{label}</p>
      <p className="flex flex-wrap items-baseline gap-x-1.5" style={{ fontVariantNumeric: "tabular-nums" }}>
        <span className="text-[13px] font-bold text-white">{fmt(m.value)}</span>
        {m.chg_1w != null && <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>주간 {chgFmt(m.chg_1w)}</span>}
      </p>
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
// 칸마다 카드 하나 + 제목·건수 한 줄로, 비슷한 칸끼리 묶음 제목 아래 둔다.
// 스크롤 여백: 위에 붙는 주 선택 띠 높이(휴대폰은 목차 줄까지)만큼
const SCROLL_M = "scroll-mt-28 lg:scroll-mt-20";
function Section({ id, title, count, sub, tone, children }: {
  id: string; title: ReactNode; count?: ReactNode; sub?: ReactNode; tone?: "mine" | "warm"; children: ReactNode;
}) {
  const box = tone === "mine" ? { background: "#f59e0b0d", border: "1px solid #f59e0b44" }
    : tone === "warm" ? { background: "#ffb02008", border: "1px solid #ffb02022" } : { border: "1px solid var(--border)" };
  const head = tone === "mine" ? "#f59e0b" : tone === "warm" ? "#ffb020" : "var(--text-primary)";
  return (
    <section id={id} className={`rounded-xl p-3 sm:p-4 ${tone ? "" : "bg-card"} ${SCROLL_M}`} style={box}>
      <div className="mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <h3 className="text-[14px] font-bold" style={{ color: head }}>{title}</h3>
        {count != null && <span className="text-[13px] font-bold" style={{ color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>{count}</span>}
        {sub && <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>{sub}</span>}
      </div>
      {children}
    </section>
  );
}
function Group({ title, children }: { title: string; children: ReactNode }) {
  // 이번 주에 보여 줄 칸이 하나도 없으면 묶음 제목도 숨긴다
  const kids = Children.toArray(children);
  if (kids.length === 0) return null;
  return (
    <div className="space-y-2">
      <h2 className="stat-label px-1 pt-3">{title}</h2>
      {kids}
    </div>
  );
}
function Sub({ children }: { children: ReactNode }) {
  return <p className="text-[12px] font-semibold mt-3 first:mt-0 mb-1" style={{ color: "var(--text-secondary)" }}>{children}</p>;
}
// 긴 목록은 처음 몇 줄만, 나머지는 "더 보기"로(브리핑 한 주 분량이 공시·내부자만 100줄 넘게 나온다)
function More<T>({ items, n = 5, render, className = "space-y-1" }: { items: T[]; n?: number; render: (x: T) => ReactNode; className?: string }) {
  const [all, setAll] = useState(false);
  return (
    <>
      <div className={className}>{(all ? items : items.slice(0, n)).map(render)}</div>
      {items.length > n && (
        <button onClick={() => setAll(!all)} className="mt-1.5 text-[12px] hover:underline" style={{ color: "#ffb020" }}>
          {all ? "접기" : `더 보기 (+${items.length - n})`}
        </button>
      )}
    </>
  );
}
const byMarket = (m: Record<string, number>, unit = "") =>
  Object.entries(m).sort(([a], [c]) => c.localeCompare(a)).map(([k, n]) => `${k === "KR" ? "한국" : "미국"} ${n}${unit}`).join(" · ");

type TocItem = { id: string; label: string; count?: string; group: string };

function BriefingView({ b, picker }: { b: Briefing; picker: ReactNode }) {
  const wl = b.watchlist ?? { total: 0, added: [], removed: [], top: [], has_prev: false };
  const [active, setActive] = useState("");
  const [commentOpen, setCommentOpen] = useState(false);
  const chipsRef = useRef<HTMLDivElement>(null);

  const has = {
    mine: (b.my_stocks_week?.count ?? 0) > 0,
    comment: !!b.gpt_comment,
    labels: !!b.theme_labels && (b.theme_labels.new_labels.length > 0 || b.theme_labels.dropped_labels.length > 0),
    earnings: (b.earnings_week?.total ?? 0) > 0,
    catalysts: (b.catalysts?.length ?? 0) > 0,
    disclosures: !!b.kr_disclosures && discTotal(b) > 0,
    us8k: (b.us_8k_week?.total ?? 0) > 0,
    insider: (b.insider_week?.total ?? 0) > 0,
    turnaround: !!b.turnaround,
    sentiment: (b.sentiment_heating?.length ?? 0) > 0,
  };
  // 목차 - 아래 칸 순서 그대로. 앵커는 개요 "이번 주 변화"·⭐ 줄이 쓰는 짧은 이름(#earnings 등)
  const toc: TocItem[] = [
    ...(has.mine ? [{ id: "mine", label: "⭐ 관심 종목", count: `${b.my_stocks_week!.count}`, group: "" }] : []),
    ...(has.comment ? [{ id: "comment", label: "총평", group: "" }] : []),
    { id: "market", label: "지난주 시장", group: "시장" },
    ...(has.earnings ? [{ id: "earnings", label: "실적 발표", count: `${b.earnings_week!.total}`, group: "이번 주 일정" }] : []),
    ...(has.catalysts ? [{ id: "catalysts", label: "촉매", count: `${b.catalysts.length}`, group: "이번 주 일정" }] : []),
    ...(has.disclosures ? [{ id: "disclosures", label: "한국 공시", count: `${discTotal(b)}`, group: "공시 · 내부자" }] : []),
    ...(has.us8k ? [{ id: "us8k", label: "미국 8-K", count: `${b.us_8k_week!.total}`, group: "공시 · 내부자" }] : []),
    ...(has.insider ? [{ id: "insider", label: "내부자 매수", count: `${b.insider_week!.total}`, group: "공시 · 내부자" }] : []),
    { id: "watchlist", label: "워치리스트",
      count: wl.has_prev ? `+${wl.added_count ?? wl.added.length} −${wl.removed_count ?? wl.removed.length}` : undefined, group: "종목 변화" },
    ...(has.turnaround ? [{ id: "turnaround", label: "실적 반전", count: b.turnaround!.has_prev ? `+${b.turnaround!.added_count}` : undefined, group: "종목 변화" }] : []),
    ...(has.sentiment ? [{ id: "sentiment", label: "관심도", count: `${b.sentiment_heating.length}`, group: "종목 변화" }] : []),
    ...(has.labels ? [{ id: "labels", label: "테마 라벨",
      count: `${b.theme_labels!.new_labels.length + b.theme_labels!.dropped_labels.length}`, group: "테마" }] : []),
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
            <Section id="mine" tone="mine" title="⭐ 관심 종목에 생긴 일"
              sub={`내 관심·노트 ${b.my_stocks_week!.watched}종목 중 ${b.my_stocks_week!.count}종목`}>
              <div className="divide-y" style={{ borderColor: "#f59e0b22" }}>
                {b.my_stocks_week!.items.map((x) => (
                  <div key={`${x.market}:${x.symbol}`} className="py-1.5 first:pt-0 last:pb-0" style={{ borderColor: "#f59e0b22" }}>
                    <div className="flex flex-wrap items-center gap-1.5 text-[13px]">
                      <StockLabel s={x} /><DiscTags tags={x.tags} />
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
              <Note>아래 칸(실적 발표·한국 공시·미국 8-K·내부자 매수·실적 반전)과 노트 회고에서 내 관심·노트 종목 줄만 모았습니다 · 누르면 그 칸으로</Note>
            </Section>
          )}

          {has.comment && (
            <Section id="comment" tone="warm" title="주간 총평">
              <p className={`text-[13px] leading-relaxed whitespace-pre-line ${longComment && !commentOpen ? "line-clamp-4" : ""}`} style={{ color: "#bdb5a0" }}>
                {b.gpt_comment}
              </p>
              {longComment && (
                <button onClick={() => setCommentOpen(!commentOpen)} className="mt-1 text-[12px] hover:underline" style={{ color: "#ffb020" }}>
                  {commentOpen ? "접기" : "전체 보기"}
                </button>
              )}
            </Section>
          )}

          <Group title="시장">
            <Section id="market" title="지난주 시장">
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
              {b.macro && (
                <div className="mt-1.5 grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                  <MacroRow label="미 10년물" m={b.macro.us10y}
                    fmt={(v) => `${v.toFixed(2)}%`} chgFmt={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%p`} />
                  <MacroRow label="미 실질금리" m={b.macro.real10y}
                    fmt={(v) => `${v.toFixed(2)}%`} chgFmt={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%p`} />
                  <MacroRow label="하이일드 스프레드" m={b.macro.hy_spread}
                    fmt={(v) => `${v.toFixed(2)}%p`} chgFmt={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%p`} />
                  <MacroRow label="국고채 3년" m={b.macro.kr3y}
                    fmt={(v) => `${v.toFixed(2)}%`} chgFmt={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%p`} />
                  <MacroRow label="원/달러" m={b.macro.usdkrw}
                    fmt={(v) => `${Math.round(v).toLocaleString()}원`} chgFmt={(v) => `${v >= 0 ? "+" : ""}${Math.round(v).toLocaleString()}원`} />
                  <MacroRow label="달러인덱스" m={b.macro.dxy}
                    fmt={(v) => v.toFixed(1)} chgFmt={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}`} />
                  <MacroRow label="WTI 유가" m={b.macro.wti} fmt={(v) => `$${v.toFixed(1)}`} chgFmt={usdChg(b.macro.wti)} />
                  <MacroRow label="구리" m={b.macro.copper} fmt={(v) => `$${v.toFixed(2)}/lb`} chgFmt={usdChg(b.macro.copper)} />
                  <MacroRow label="천연가스" m={b.macro.natgas} fmt={(v) => `$${v.toFixed(2)}`} chgFmt={usdChg(b.macro.natgas)} />
                </div>
              )}
            </Section>
          </Group>

          <Group title="이번 주 일정">
            {has.earnings && (
              <Section id="earnings" title="실적 발표" count={b.earnings_week!.total} sub={byMarket(b.earnings_week!.by_market)}>
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
                <Note>워치리스트 후보·내 관심·관찰 노트 종목 · 날짜는 yfinance(회사 공지 전이면 &quot;예상&quot;), 한국은 결산실적 공시예고가 있으면 그 날짜 · 노란 칸이 내 관심·노트·실적 반전</Note>
              </Section>
            )}
            {has.catalysts && (
              <Section id="catalysts" title="다가오는 촉매" count={b.catalysts.length} sub="내 워치리스트">
                <More items={b.catalysts} render={(s) => (
                  <div key={`${s.market}:${s.symbol}`} className="rounded-lg px-3 py-2" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                    <StockLabel s={s} />
                    {(s.catalysts ?? []).map((c, i) => (
                      <p key={i} className="text-[12px] mt-0.5 pl-1" style={{ color: "var(--text-muted)" }}>▲ {c}</p>
                    ))}
                  </div>
                )} />
              </Section>
            )}
          </Group>

          <Group title="공시 · 내부자">
            {has.disclosures && (() => {
              const k = b.kr_disclosures!;
              const fix = [...(k.termination?.items ?? []), ...(k.amend?.items ?? [])];
              return (
                <Section id="disclosures" title="🇰🇷 한국 공시" count={discTotal(b)}
                  sub={[`지난 7일`, `공급계약 ${k.contract.count}`, `잠정실적 ${k.prelim.count}`,
                    ...((k.termination?.count ?? 0) > 0 ? [`해지 ${k.termination!.count}`] : []),
                    ...((k.amend?.count ?? 0) > 0 ? [`정정 ${k.amend!.count}`] : [])].join(" · ")}>
                  {fix.length > 0 && (
                    <>
                      <Sub>계약 해지 · 계약금액 정정 <span className="font-normal" style={{ color: "var(--text-muted)" }}>(날짜만 바뀐 정정은 뺌)</span></Sub>
                      <More items={fix} render={(d) => (
                        <div key={d.rcept_no} className="flex items-center gap-2 flex-wrap text-[12px] rounded-lg px-3 py-1.5"
                          style={{ background: "#f8717110", border: `1px solid ${d.tags.length > 0 ? "#f59e0b55" : "#f8717133"}` }}>
                          <span className="w-11 shrink-0 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>{d.date.slice(5).replace("-", "/")}</span>
                          <DiscName d={d} />
                          <span style={{ color: "#fca5a5" }}>{d.summary}</span>
                          <DiscTags tags={d.tags} />
                        </div>
                      )} />
                    </>
                  )}
                  {k.contract.items.length > 0 && (
                    <>
                      <Sub>공급계약 <span className="font-normal" style={{ color: "var(--text-muted)" }}>관심 종목 먼저, 그다음 매출 대비 큰 순</span></Sub>
                      <More items={k.contract.items} render={(d) => (
                        <div key={d.rcept_no} className="flex items-center gap-2 flex-wrap text-[12px] rounded-lg px-3 py-1.5"
                          style={d.tags.length > 0 ? { background: "#f59e0b14", border: "1px solid #f59e0b55" } : { background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                          <span className="w-11 shrink-0 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>{d.date.slice(5).replace("-", "/")}</span>
                          <DiscName d={d} />
                          <span className="text-white">{d.withheld ? "금액 비공개" : eok(d.amount)}</span>
                          {d.pct != null && <span style={{ color: d.pct >= 10 ? "#4ade80" : "var(--text-secondary)" }}>매출 대비 {d.pct.toFixed(1)}%</span>}
                          {d.title && <span className="truncate max-w-[16rem]" style={{ color: "var(--text-secondary)" }}>{d.title}</span>}
                          <DiscTags tags={d.tags} />
                        </div>
                      )} />
                    </>
                  )}
                  {k.prelim.items.length > 0 && (
                    <>
                      <Sub>잠정실적 <span className="font-normal" style={{ color: "var(--text-muted)" }}>전년 같은 분기 대비, 회사가 공시한 증감률</span></Sub>
                      <More items={k.prelim.items} render={(d) => (
                        <div key={d.rcept_no} className="flex items-center gap-2 flex-wrap text-[12px] rounded-lg px-3 py-1.5"
                          style={d.tags.length > 0 ? { background: "#f59e0b14", border: "1px solid #f59e0b55" } : { background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                          <span className="w-11 shrink-0 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>{d.date.slice(5).replace("-", "/")}</span>
                          <DiscName d={d} />
                          {d.quarter && <span style={{ color: "var(--text-muted)" }}>{d.quarter}</span>}
                          <YoY label="매출" pct={d.revenue_yoy_pct} turn={d.revenue_yoy_turn} />
                          <YoY label="영업익" pct={d.operating_income_yoy_pct} turn={d.operating_income_yoy_turn} />
                          <DiscTags tags={d.tags} />
                        </div>
                      )} />
                    </>
                  )}
                  {(k.contract.count > k.contract.items.length || k.prelim.count > k.prelim.items.length) && (
                    <p className="text-[12px] mt-1" style={{ color: "var(--text-muted)" }}>목록은 종류별 30건까지</p>
                  )}
                  <Note>시총 3000억 이상 또는 관심 종목(내 관심·노트·워치리스트·테마) · 정정·자회사 공시 제외 · 이름을 누르면 종목 상세, 원문↗은 DART 공시</Note>
                </Section>
              );
            })()}

            {has.us8k && (
              <Section id="us8k" title="🇺🇸 미국 8-K" count={b.us_8k_week!.total}
                sub={`지난 7일 · ${Object.entries(b.us_8k_week!.by_kind).map(([k, n]) => `${k} ${n}`).join(" · ")}`}>
                <More items={b.us_8k_week!.items} render={(x) => (
                  <div key={`${x.symbol}-${x.date}-${x.items.map((i) => i.item).join()}`} className="text-[12px] rounded-lg px-3 py-1.5"
                    style={x.warn ? { background: "#f8717110", border: "1px solid #f8717144" }
                      : x.tags.length > 0 ? { background: "#f59e0b14", border: "1px solid #f59e0b55" } : { background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="w-11 shrink-0 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>{x.date.slice(5).replace("-", "/")}</span>
                      <StockLabel s={x} />
                      {x.url && <a href={x.url} target="_blank" rel="noreferrer" className="text-[11px] hover:underline" style={{ color: "var(--text-muted)" }}>원문↗</a>}
                      {x.items.map((i) => (
                        <span key={i.item} style={{ color: i.warn ? "#f87171" : "var(--text-secondary)" }}>{i.label}</span>
                      ))}
                      <DiscTags tags={x.tags} />
                    </div>
                    {x.items.filter((i) => i.excerpt).slice(0, 1).map((i) => (
                      <p key={i.item} className="text-[12px] mt-0.5 line-clamp-2" style={{ color: "var(--text-muted)" }} title={i.excerpt ?? ""}>
                        {i.excerpt}
                      </p>
                    ))}
                  </div>
                )} />
                {b.us_8k_week!.total > b.us_8k_week!.items.length && (
                  <p className="text-[12px] mt-1" style={{ color: "var(--text-muted)" }}>목록은 {b.us_8k_week!.items.length}건까지</p>
                )}
                <Note>관심 종목(워치리스트·내 관심·노트·테마)의 8-K · 항목 번호로 나눈 종류, 아래 줄은 공시 원문 첫머리(번역·요약 없음) ·
                  실적 발표만 있는 8-K는 뺌 · 붉은 칸은 계약 해지·구조조정·손상·감사인 교체 등 · 임원 변동의 사임/선임은 낱말로 나눈 것</Note>
              </Section>
            )}

            {has.insider && (() => {
              const ins = b.insider_week!;
              return (
                <Section id="insider" title="내부자 장내 매수" count={ins.total} sub={`지난 7일 공시 · ${byMarket(ins.by_market, "종목")}`}>
                  {ins.discovery ? (
                    <>
                      {ins.items.length > 0 && (
                        <>
                          <Sub>관심 종목 {ins.tagged_count ?? ins.items.length}</Sub>
                          <More items={ins.items} render={(x) => <InsiderRow key={`${x.market}:${x.symbol}`} x={x} />} />
                        </>
                      )}
                      {ins.discovery.length > 0 && (
                        <>
                          <Sub>🆕 관심 밖 — 새 이름 {ins.discovery_count ?? ins.discovery.length}{" "}
                            <span className="font-normal" style={{ color: "var(--text-muted)" }}>산 사람 수 → 금액 순, 계획 매수만 있는 종목은 뒤로</span></Sub>
                          <More items={ins.discovery} render={(x) => <InsiderRow key={`${x.market}:${x.symbol}`} x={x} showFinance />} />
                        </>
                      )}
                    </>
                  ) : (
                    <More items={ins.items} render={(x) => <InsiderRow key={`${x.market}:${x.symbol}`} x={x} />} />
                  )}
                  <Note>임원·이사·대주주가 장내에서 직접 산 것만(스톡옵션·증여·장외 제외) · 금액은 공시 단가 × 주식 수 합계 · 목록은 각 30종목까지
                    {ins.discovery && " · 관심 밖은 미국 S&P 500·400, 한국 시총 3000억+ 중 관심 표시 없는 종목, 재무는 트랩 필터 판정(통과·탈락·데이터부족)"}</Note>
                </Section>
              );
            })()}
          </Group>

          <Group title="종목 변화">
            <Section id="watchlist" title="워치리스트 변동" sub={`후보 ${wl.total}개`}>
              {!wl.has_prev ? (
                <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>첫 스냅샷 주간 — 다음 주부터 신규/탈락 비교가 표시돼요.</p>
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
              <Section id="turnaround" title="실적 반전"
                sub={`${byMarket(b.turnaround!.by_market) || "0"}${b.turnaround!.has_prev ? ` · 새로 ${b.turnaround!.added_count} · 빠짐 ${b.turnaround!.removed_count}` : ""}`}>
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
              <Section id="sentiment" title="관심도 상승" count={b.sentiment_heating.length}>
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
          </Group>

          {/* 테마 레이더 라벨 변동 — 라벨 계산은 별도 워크플로우라 이 브리핑보다 늦게
              끝날 수 있어서, "이번 주"라 단정하지 않고 실제 기준 주를 그대로 보여준다. */}
          <Group title="테마">
            {has.labels && (
              <Section id="labels" title="📡 테마 레이더 라벨 변동" sub={`${b.theme_labels!.week_start} 기준`}>
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
          </Group>
        </div>

        {/* 넓은 화면 목차 - 묶음별, 지금 읽는 칸 표시 */}
        <aside className="hidden lg:block">
          <nav className="sticky top-12 space-y-3" aria-label="브리핑 목차">
            {groups.map((g) => (
              <div key={g || "top"}>
                {g && <p className="stat-label mb-1">{g}</p>}
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

  useEffect(() => {
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
        desc="지난주를 돌아보고 이번 주를 준비하는 문서. 한 주씩 봅니다 - 맨 위 ⭐ 관심 종목에 생긴 일부터, 목차를 누르면 그 칸으로." />

      {loading ? (
        <div className="h-24 rounded-xl animate-pulse" style={{ background: "#111009" }} />
      ) : !b ? (
        <EmptyState title="아직 브리핑이 없어요"
          hint="매주 일요일 밤 워치리스트 스크리닝 뒤 자동으로 만들어집니다. 지금 만들려면 GitHub → Actions → Weekly Watchlist Screen → Run workflow" />
      ) : (
        <BriefingView key={b.week} b={b}
          picker={<WeekPicker weeks={briefings.map((x) => x.week)} idx={idx} onPick={pick} generatedAt={b.generated_at} />} />
      )}
    </div>
  );
}
