"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import StockLink from "@/src/components/StockLink";
import { themeName } from "@/src/lib/themeNames";
import { useMarket } from "@/src/contexts/MarketContext";
import { krStockName } from "@/src/lib/krStockNames";
import PageHeader from "@/src/components/PageHeader";
import EmptyState from "@/src/components/EmptyState";

// docs/SPEC_quarterly_screen.md 구현. 색·톤은 app/radar/page.tsx의 토큰을 그대로 쓴다
// (새로 만들지 않는다 - 이 파일이 별도 상수로 다시 갖고 있는 건 그 파일도 그렇게
// 하고 있는 기존 관례를 따른 것이다).
const ACCENT = "var(--accent)";
const ACCENT_SOFT = "rgba(255,176,32,0.14)";
const GOOD = "var(--good)";
const GOOD_SOFT = "rgba(74,222,128,0.14)";
const DANGER = "var(--danger)";
const DANGER_SOFT = "rgba(248,113,113,0.14)";
const MUTED = "var(--text-muted)";
const MUTED_SOFT = "rgba(139,130,113,0.14)";
const FAINT = "var(--text-faint)";
const INFO = "var(--info)";
const INFO_SOFT = "rgba(111,179,184,0.15)";
const SECONDARY_SOFT = "rgba(236,231,216,0.10)";
const MONO = 'ui-monospace, "SF Mono", "Cascadia Code", "Roboto Mono", monospace';

type Classification = "조용한 변화" | "확인된 변화" | "기대 선행" | "관심 밖";
const CLASSIFICATIONS: Classification[] = ["조용한 변화", "확인된 변화", "기대 선행", "관심 밖"];

// SPEC 0장 - 편집 방침. "두 축이 어긋나는 자리가 가장 쓸모 있다."
// bg는 테마 줄의 분류 배지용 - 2×2 그리드(강조는 조용한 변화에만)와 달리, 여기서는
// 4칸이 섞여 보이는 자리가 없어(섹션별로 이미 나뉘어 있다) 배지 색은 구분 목적으로
// 4칸 다 다르게 준다. 전부 같은 색이면 필터 없이 스크롤할 때 지금 어느 섹션인지
// 배지만 보고는 못 알아본다.
const CLASSIFICATION_INFO: Record<Classification, { desc: string; color: string; bg: string; emphasis?: boolean }> = {
  "조용한 변화": {
    desc: "실적이 먼저 움직였는데 시장은 아직 모릅니다. 이 화면이 있는 이유입니다.",
    color: ACCENT, bg: ACCENT_SOFT,
    emphasis: true,
  },
  "확인된 변화": {
    desc: "재무·뉴스 둘 다 맞았지만 남들도 이미 압니다. 밸류 위치를 꼭 확인하세요.",
    color: INFO, bg: INFO_SOFT,
  },
  "기대 선행": {
    desc: "기대가 먼저 붙었습니다. 다음 분기 재무가 따라오는지 지켜볼 구간입니다.",
    color: "var(--text-secondary)", bg: SECONDARY_SOFT,
  },
  "관심 밖": {
    desc: "이번 분기엔 재무도 뉴스도 특별한 움직임이 없습니다.",
    color: MUTED, bg: MUTED_SOFT,
  },
};

interface ThemeQuarterly {
  theme_id: string;
  classification: string | null;
  financial_on: boolean | null;
  financial_changed: number | null;
  financial_judged: number | null;
  financial_ratio: number | null;
  news_high: boolean | null;
  news_ratio: number | null;
  news_this_quarter: number | null;
  previous_classification: string | null;
}

interface MarketReference {
  median_revenue_growth: number | null;
  sample_size: number;
}

interface CompanySignal {
  ticker: string;
  revenue_transition: boolean | null;
  revenue_flow: boolean | null;
  profit_transition: boolean | null;
  changed: boolean | null;
  revenue_recent: number | null;
  revenue_year_ago: number | null;
  psr: number | null;
  per: number | null;
  valuation_tier: string | null;
  finance: { status: string; piotroski: number | null; reasons: string[] };
}

// ── 표시 도우미 ──────────────────────────────────────────────

function changedDisplay(t: ThemeQuarterly): string {
  if (t.financial_on === null) {
    return `판정 가능 기업 부족${t.financial_judged != null ? ` (${t.financial_judged}곳)` : ""}`;
  }
  const pctStr = t.financial_ratio != null ? ` (${Math.round(t.financial_ratio * 100)}%)` : "";
  return `${t.financial_changed ?? "-"}/${t.financial_judged ?? "-"}${pctStr}`;
}

function newsDisplay(t: ThemeQuarterly): string {
  if (t.news_ratio == null) return "-";
  return `${t.news_ratio.toFixed(2)}배`;
}

function prevDisplay(t: ThemeQuarterly): string {
  if (t.previous_classification == null) return "지난 분기 기록 없음";
  if (t.classification && t.previous_classification !== t.classification) {
    return `${t.previous_classification} → ${t.classification}`;
  }
  return `지난 분기 ${t.previous_classification}`;
}

// SPEC 2-4 - 데이터부족 "왜 못 들어갔는지".
function naReason(t: ThemeQuarterly): string {
  const finMissing = t.financial_on === null;
  const newsMissing = t.news_high === null;
  if (finMissing && newsMissing) return "재무·뉴스 둘 다 부족";
  if (finMissing) return `판정 가능 기업 부족${t.financial_judged != null ? ` (${t.financial_judged}곳)` : ""}`;
  if (newsMissing) return "뉴스 이력 부족";
  return "";
}

function pctGrowth(n: number | null): string {
  if (n == null) return "계산불가";
  const v = (n * 100).toFixed(1);
  return `${n >= 0 ? "+" : ""}${v}%`;
}

// 매출은 원 단위로 저장돼 있다. 한국은 억원, 미국은 백만 달러로 보여준다
// (scripts/collect_kr_quarterly_financials.py·collect_us_quarterly_financials.py의
// 확인용 표 출력과 같은 단위를 써서, 사람이 운영 로그와 화면을 같은 감각으로 읽게 한다).
function fmtRevenue(v: number | null, market: string): string {
  if (v == null) return "-";
  const divisor = market === "KR" ? 1e8 : 1e6;
  const unit = market === "KR" ? "억" : "M";
  return `${Math.round(v / divisor).toLocaleString("ko-KR")}${unit}`;
}

function sortThemes(items: ThemeQuarterly[]): ThemeQuarterly[] {
  return [...items].sort((a, b) => {
    const ra = a.financial_ratio ?? -1, rb = b.financial_ratio ?? -1;
    if (rb !== ra) return rb - ra;
    const ca = a.financial_changed ?? -1, cb = b.financial_changed ?? -1;
    if (cb !== ca) return cb - ca;
    return a.theme_id.localeCompare(b.theme_id);
  });
}

function sortMembers(members: CompanySignal[]): CompanySignal[] {
  return [...members].sort((a, b) => {
    const ca = a.changed === true ? 0 : a.changed === false ? 1 : 2;
    const cb = b.changed === true ? 0 : b.changed === false ? 1 : 2;
    if (ca !== cb) return ca - cb;
    const pa = a.psr ?? Infinity, pb = b.psr ?? Infinity;
    return pa - pb;
  });
}

// ── 작은 컴포넌트 ────────────────────────────────────────────

// SPEC 3-4 - "-"(데이터부족)와 X(탈락)를 절대 같은 모양으로 그리지 않는다.
function TriChip({ label, value }: { label: string; value: boolean | null }) {
  const style =
    value === null
      ? { color: FAINT, opacity: 0.55 }
      : value
      ? { color: GOOD, fontWeight: 700 }
      : { color: MUTED };
  return (
    <div className="flex flex-col items-center gap-0.5">
      <span className="text-[11px]" style={{ color: MUTED }}>{label}</span>
      <span className="text-[13px]" style={{ fontFamily: MONO, ...style }}>
        {value === null ? "–" : value ? "O" : "X"}
      </span>
    </div>
  );
}

function ChangedBadge({ value }: { value: boolean | null }) {
  if (value === null) {
    return (
      <span className="whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px]" style={{ color: FAINT, border: "1px solid var(--border)" }}>
        데이터부족
      </span>
    );
  }
  return value ? (
    <span className="whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-bold" style={{ background: GOOD_SOFT, color: GOOD }}>
      변화 기업
    </span>
  ) : (
    <span className="whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px]" style={{ background: MUTED_SOFT, color: MUTED }}>
      -
    </span>
  );
}

function ValuationTierBadge({ tier }: { tier: string | null }) {
  if (!tier) return null;
  const style =
    tier === "싼 편" ? { background: GOOD_SOFT, color: GOOD } :
    tier === "비싼 편" ? { background: DANGER_SOFT, color: DANGER } :
    { background: MUTED_SOFT, color: MUTED };
  return (
    <span className="self-start whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold" style={style}>
      {tier}
    </span>
  );
}

// 기존 주간 화면의 FinanceBadge와 같은 요약 방식(SPEC 5-3: 기존 로직 그대로).
function shortReason(flag: string): string {
  if (flag.startsWith("Piotroski")) return "F-Score";
  if (flag.startsWith("ROE")) return "ROE";
  if (flag.startsWith("부채비율")) return "부채";
  if (flag.startsWith("이자보상")) return "이자보상";
  if (flag.includes("현금흐름")) return "현금흐름";
  if (flag.includes("감소")) return "매출감소";
  return flag.split(" ")[0];
}

function FinanceBadge({ finance }: { finance: CompanySignal["finance"] }) {
  const base = "whitespace-nowrap rounded-full px-2 py-0.5 text-[10.5px]";
  if (finance.status === "pass") {
    return (
      <span className={`${base} font-semibold`} style={{ background: GOOD_SOFT, color: GOOD }}>
        통과{finance.piotroski != null && ` (F${finance.piotroski})`}
      </span>
    );
  }
  if (finance.status === "fail") {
    const shown = Array.from(new Set((finance.reasons ?? []).map(shortReason))).slice(0, 2);
    return (
      <span className={`${base} font-semibold`} style={{ background: DANGER_SOFT, color: DANGER }} title={(finance.reasons ?? []).join(" / ")}>
        탈락{shown.length > 0 && ` (${shown.join("·")})`}
      </span>
    );
  }
  if (finance.status === "insufficient") {
    return <span className={base} style={{ background: MUTED_SOFT, color: MUTED }}>데이터부족</span>;
  }
  return <span className={base} style={{ color: FAINT, border: "1px solid var(--border)" }}>미확인</span>;
}

// ── 2×2 분류 그리드 (필터 겸용) ──────────────────────────────

function GridCell({ label, count, active, emphasis, onClick }: {
  label: Classification; count: number; active: boolean; emphasis?: boolean; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex flex-col items-center justify-center gap-0.5 rounded-lg px-3 py-3.5 text-center transition-all"
      style={{
        background: active ? ACCENT_SOFT : emphasis ? ACCENT_SOFT : "var(--bg-inset)",
        border: active ? `1.5px solid ${ACCENT}` : "1px solid var(--border)",
        opacity: emphasis || active ? 1 : 0.85,
      }}
    >
      <span className="text-[13px] font-bold" style={{ color: active || emphasis ? ACCENT : "var(--text-primary)" }}>{label}</span>
      <span className="text-[19px] font-extrabold" style={{ fontFamily: MONO, color: "var(--text-primary)" }}>{count}</span>
    </button>
  );
}

function ClassificationGrid({ counts, filter, onToggle }: {
  counts: Record<Classification, number>; filter: Classification | null; onToggle: (c: Classification) => void;
}) {
  return (
    <div className="mt-4 grid max-w-2xl gap-2" style={{ gridTemplateColumns: "64px 1fr 1fr" }}>
      <div />
      <div className="pb-1 text-center text-[12px]" style={{ color: MUTED }}>뉴스 적음</div>
      <div className="pb-1 text-center text-[12px]" style={{ color: MUTED }}>뉴스 많음</div>

      <div className="flex items-center justify-end pr-2 text-[12px]" style={{ color: MUTED }}>재무 켜짐</div>
      <GridCell label="조용한 변화" count={counts["조용한 변화"]} active={filter === "조용한 변화"} emphasis onClick={() => onToggle("조용한 변화")} />
      <GridCell label="확인된 변화" count={counts["확인된 변화"]} active={filter === "확인된 변화"} onClick={() => onToggle("확인된 변화")} />

      <div className="flex items-center justify-end pr-2 text-[12px]" style={{ color: MUTED }}>재무 꺼짐</div>
      <GridCell label="관심 밖" count={counts["관심 밖"]} active={filter === "관심 밖"} onClick={() => onToggle("관심 밖")} />
      <GridCell label="기대 선행" count={counts["기대 선행"]} active={filter === "기대 선행"} onClick={() => onToggle("기대 선행")} />
    </div>
  );
}

// ── 소속 기업 표 ─────────────────────────────────────────────

function MembersTable({ members, loading, market }: { members: CompanySignal[]; loading: boolean; market: string }) {
  const [changedOnly, setChangedOnly] = useState(false);
  const [passOnly, setPassOnly] = useState(false);
  const [cheapOnly, setCheapOnly] = useState(false);

  if (loading) return <div className="py-4 text-[12px]" style={{ color: MUTED }}>불러오는 중...</div>;
  if (members.length === 0) return <div className="py-4 text-[12px]" style={{ color: MUTED }}>회사별 신호를 찾을 수 없습니다.</div>;

  const filtered = sortMembers(members).filter((m) => {
    if (changedOnly && m.changed !== true) return false;
    if (passOnly && m.finance.status !== "pass") return false;
    if (cheapOnly && m.valuation_tier !== "싼 편") return false;
    return true;
  });

  const toggleBtn = (active: boolean, label: string, onClick: () => void) => (
    <button
      onClick={onClick}
      className="whitespace-nowrap rounded-lg px-2.5 py-1 text-[11.5px] font-semibold"
      style={{ border: "1px solid var(--border)", color: active ? ACCENT : MUTED, background: active ? ACCENT_SOFT : "transparent" }}
    >
      {label}
    </button>
  );

  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-1.5">
        {toggleBtn(changedOnly, "변화 기업만", () => setChangedOnly((v) => !v))}
        {toggleBtn(passOnly, "재무 통과만", () => setPassOnly((v) => !v))}
        {toggleBtn(cheapOnly, "밸류 싼 편만", () => setCheapOnly((v) => !v))}
      </div>
      <div className="overflow-x-auto rounded-lg" style={{ border: "1px solid var(--border)" }}>
        <table className="w-full text-[13px]" style={{ borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "var(--bg-inset)" }}>
              {[market === "KR" ? "종목" : "티커", "변화 신호", "변화 기업", "매출(1년전→최근)", "밸류", "재무"].map((h) => (
                <th key={h} className="whitespace-nowrap px-3 py-2 text-left text-[12px] font-bold" style={{ color: MUTED, borderBottom: "1px solid var(--border)" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((m) => (
              <tr key={m.ticker} style={{ borderBottom: "1px solid var(--border)" }}>
                <td className="px-3 py-2 align-top">
                  {market === "KR" ? (
                    <div className="flex flex-col">
                      <StockLink market="KR" symbol={m.ticker} className="whitespace-nowrap font-bold" style={{ color: "var(--text-primary)" }}>{krStockName(m.ticker)}</StockLink>
                      <span className="text-[12px]" style={{ fontFamily: MONO, color: MUTED }}>{m.ticker}</span>
                    </div>
                  ) : (
                    <StockLink market="US" symbol={m.ticker} className="font-bold" style={{ fontFamily: MONO, color: "var(--num)" }}>{m.ticker}</StockLink>
                  )}
                </td>
                <td className="px-3 py-2 align-top">
                  <div className="flex gap-3">
                    <TriChip label="매출전환" value={m.revenue_transition} />
                    <TriChip label="매출흐름" value={m.revenue_flow} />
                    <TriChip label="이익전환" value={m.profit_transition} />
                  </div>
                </td>
                <td className="px-3 py-2 align-top"><ChangedBadge value={m.changed} /></td>
                <td className="px-3 py-2 align-top text-[12.5px]" style={{ fontFamily: MONO, color: MUTED }}>
                  {fmtRevenue(m.revenue_year_ago, market)} → {fmtRevenue(m.revenue_recent, market)}
                </td>
                <td className="px-3 py-2 align-top">
                  <div className="flex flex-col gap-1">
                    <span className="text-[12px]" style={{ fontFamily: MONO, color: "var(--text-primary)" }}>
                      PSR {m.psr != null ? m.psr.toFixed(2) : "-"}
                    </span>
                    <span className="text-[11px]" style={{ fontFamily: MONO, color: FAINT }}>
                      PER {m.per != null ? m.per.toFixed(1) : "-"}
                    </span>
                    <ValuationTierBadge tier={m.valuation_tier} />
                  </div>
                </td>
                <td className="px-3 py-2 align-top"><FinanceBadge finance={m.finance} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length === 0 && (
        <div className="py-3 text-center text-[12px]" style={{ color: MUTED }}>필터에 맞는 기업이 없습니다.</div>
      )}
    </div>
  );
}

// ── 테마 한 줄 ───────────────────────────────────────────────

function ThemeRow({ theme, market, isNa }: { theme: ThemeQuarterly; market: string; isNa?: boolean }) {
  const [open, setOpen] = useState(false);
  const [members, setMembers] = useState<CompanySignal[] | null>(null);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const { ko, en } = themeName(theme.theme_id);

  const toggle = useCallback(() => {
    setOpen((o) => !o);
    if (!members && !loadingMembers) {
      setLoadingMembers(true);
      fetch(`/api/quarterly/members?theme_id=${encodeURIComponent(theme.theme_id)}&market=${market}`)
        .then((r) => r.json())
        .then((d) => setMembers(d.members ?? []))
        .catch(() => setMembers([]))
        .finally(() => setLoadingMembers(false));
    }
  }, [members, loadingMembers, theme.theme_id, market]);

  return (
    <div className="mb-2.5 overflow-hidden rounded-xl" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
      <button
        onClick={toggle}
        className="flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left"
        style={{ cursor: "pointer" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-raised)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      >
        <div className="flex min-w-[150px] shrink-0 flex-col gap-0.5">
          <span className="text-[15px] font-bold" style={{ color: "var(--text-primary)" }}>{ko}</span>
          <span className="text-[11.5px]" style={{ color: FAINT }}>{en}</span>
        </div>

        {!isNa && (() => {
          const info = CLASSIFICATION_INFO[theme.classification as Classification];
          return (
            <span className="whitespace-nowrap rounded-full px-2.5 py-1 text-[11.5px] font-bold"
                  style={{ background: info?.bg ?? ACCENT_SOFT, color: info?.color ?? ACCENT }}>
              {theme.classification}
            </span>
          );
        })()}
        {isNa && (
          <span className="whitespace-nowrap rounded-full px-2.5 py-1 text-[11.5px]" style={{ color: FAINT, border: "1px solid var(--border)" }}>
            {naReason(theme)}
          </span>
        )}

        <span className="text-[12px]" style={{ color: MUTED }}>
          변화 기업 <b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>{changedDisplay(theme)}</b>
        </span>
        <span className="text-[12px]" style={{ color: MUTED }}>
          뉴스 <b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>{newsDisplay(theme)}</b>
        </span>
        <span className="ml-auto shrink-0 text-[11.5px]" style={{ color: FAINT }}>{prevDisplay(theme)}</span>
        <span className="shrink-0 text-[13px] transition-transform" style={{ color: FAINT, transform: open ? "rotate(90deg)" : "none" }}>▸</span>
      </button>

      {open && (
        <div className="px-4 pb-4" style={{ borderTop: "1px solid var(--border)" }}>
          <div className="mt-3 flex justify-end">
            <Link href={`/radar/theme?id=${encodeURIComponent(theme.theme_id)}&market=${market}`}
              className="text-[12px] font-semibold" style={{ color: ACCENT }}>
              주별 흐름 이력 보기 →
            </Link>
          </div>
          <div className="my-3">
            <MembersTable members={members ?? []} loading={loadingMembers} market={market} />
          </div>
        </div>
      )}
    </div>
  );
}

// ── 페이지 ───────────────────────────────────────────────────

export default function QuarterlyPage() {
  const { market } = useMarket();
  const [fiscalYear, setFiscalYear] = useState<number | null>(null);
  const [fiscalQuarter, setFiscalQuarter] = useState<number | null>(null);
  const [marketReference, setMarketReference] = useState<MarketReference | null>(null);
  const [themes, setThemes] = useState<ThemeQuarterly[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Classification | null>(null);
  const [showNa, setShowNa] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/quarterly?market=${market}`)
      .then((r) => r.json())
      .then((d) => {
        setFiscalYear(d.fiscal_year ?? null);
        setFiscalQuarter(d.fiscal_quarter ?? null);
        setMarketReference(d.market_reference ?? null);
        setThemes(d.themes ?? []);
      })
      .catch(() => {
        setFiscalYear(null); setFiscalQuarter(null); setMarketReference(null); setThemes([]);
      })
      .finally(() => setLoading(false));
  }, [market]);

  const grouped: Record<Classification, ThemeQuarterly[]> = {
    "조용한 변화": [], "확인된 변화": [], "기대 선행": [], "관심 밖": [],
  };
  const naThemes: ThemeQuarterly[] = [];
  themes.forEach((t) => {
    if (t.classification && (CLASSIFICATIONS as string[]).includes(t.classification)) {
      grouped[t.classification as Classification].push(t);
    } else {
      naThemes.push(t);
    }
  });
  CLASSIFICATIONS.forEach((c) => { grouped[c] = sortThemes(grouped[c]); });

  const counts = CLASSIFICATIONS.reduce((acc, c) => {
    acc[c] = grouped[c].length;
    return acc;
  }, {} as Record<Classification, number>);

  const toggleFilter = (c: Classification) => setFilter((f) => (f === c ? null : c));
  const visibleClassifications = filter ? [filter] : CLASSIFICATIONS;

  // 폭: 896px(max-w-4xl)이라 소속 기업 표가 좁고 줄바꿈이 많았다 - 워치리스트와 같은 1280px(2026-10-04)
  return (
    <div className="mx-auto max-w-[1280px]" style={{ color: "var(--text-primary)" }}>
      <PageHeader title="이번 분기 테마 4칸 분류"
        desc="순위도, 매수 추천도 없습니다. 재무 신호와 뉴스 비율 두 축을 각각 보여주고, 두 축이 어긋나는 자리를 가장 먼저 보시라고 권합니다." />

      {!loading && fiscalYear != null && (
        <p className="mt-3 text-[12px]" style={{ color: FAINT }}>
          기준 분기 {fiscalYear}Q{fiscalQuarter} · {market === "KR" ? "한국" : "미국"} 시장 · 유니버스
          매출 증가율 중앙값{" "}
          <span title="참고값입니다 - 테마 분류 판정에는 쓰지 않습니다." style={{ borderBottom: "1px dotted var(--border-ctrl)" }}>
            {marketReference ? pctGrowth(marketReference.median_revenue_growth) : "계산불가"}
            {marketReference && ` (표본 ${marketReference.sample_size}개)`}
          </span>
        </p>
      )}

      {!loading && themes.length > 0 && (
        <ClassificationGrid counts={counts} filter={filter} onToggle={toggleFilter} />
      )}

      {loading ? (
        <div className="py-16 text-center text-[13px]" style={{ color: MUTED }}>불러오는 중...</div>
      ) : themes.length === 0 ? (
        <EmptyState title="아직 계산된 분기 분류가 없습니다" hint="분기 재무 공시(미국 10-Q, 한국 분기보고서)가 나온 뒤 계산됩니다." />
      ) : (
        <>
          {visibleClassifications.map((c) => (
            <div key={c} className="mt-7">
              <div className="mb-1 flex flex-wrap items-baseline gap-2.5">
                <h2 className="text-[16px] font-extrabold" style={{ color: CLASSIFICATION_INFO[c].color }}>{c}</h2>
                <span className="text-[11.5px]" style={{ color: FAINT, fontFamily: MONO }}>{counts[c]}개</span>
              </div>
              <p className="mb-3 max-w-[68ch] text-[12.5px]" style={{ color: MUTED }}>{CLASSIFICATION_INFO[c].desc}</p>
              {grouped[c].length > 0 ? (
                grouped[c].map((t) => <ThemeRow key={t.theme_id} theme={t} market={market} />)
              ) : (
                <div className="rounded-xl px-4 py-3 text-[12.5px]"
                     style={{ border: "1px dashed var(--border-ctrl)", background: "var(--bg-inset)", color: MUTED }}>
                  이번 분기 해당 없음.
                </div>
              )}
            </div>
          ))}

          {!filter && naThemes.length > 0 && (
            <div className="mt-8">
              <button
                onClick={() => setShowNa((v) => !v)}
                className="flex items-center gap-2 text-[13px] font-semibold"
                style={{ color: MUTED }}
              >
                <span style={{ transform: showNa ? "rotate(90deg)" : "none", display: "inline-block", transition: "transform 0.15s" }}>▸</span>
                데이터부족 <span style={{ fontFamily: MONO, color: FAINT }}>{naThemes.length}개</span>
              </button>
              {showNa && (
                <div className="mt-2">
                  {naThemes.map((t) => <ThemeRow key={t.theme_id} theme={t} market={market} isNa />)}
                </div>
              )}
            </div>
          )}
        </>
      )}

      <div className="mt-12 border-t pt-5 text-[12px] leading-relaxed" style={{ borderColor: "var(--border)", color: FAINT }}>
        <p>이 화면이 하지 않는 것</p>
        <ul className="mt-1 list-disc pl-5">
          <li>종합 점수·등급 표시</li>
          <li>테마 간 순위·비교</li>
          <li>&ldquo;매수 추천&rdquo; 류의 표현</li>
        </ul>
      </div>
    </div>
  );
}
