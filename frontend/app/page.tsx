"use client";

import WelcomePanel from "@/src/components/WelcomePanel";
import { useEffect, useState, type ReactNode } from "react";
import { useMarket } from "@/src/contexts/MarketContext";
import { BigChart, RangeBar, Sparkline, lastN, type Point } from "@/src/components/MacroChart";
import AsOf from "@/src/components/AsOf";
import { LABEL_KO } from "@/src/lib/labelNames";
import { Section } from "@/src/components/Section";
import StockLink from "@/src/components/StockLink";
import { krStockName } from "@/src/lib/krStockNames";
import PageHeader from "@/src/components/PageHeader";
import SectorTurnLine from "@/src/components/SectorTurnLine";
import { quarterLabel } from "@/src/lib/institutions";
import { obsStatus, type ObservationT } from "@/src/components/Observation";
import MarketRegime, { type RegimeData } from "@/src/components/MarketRegime";

// radar/page.tsx의 편집 방침과 같은 순서 (SPEC §6.2) — 페이지별 상수 유지 관행.
const LABEL_ORDER = ["Quiet Strength", "Quiet Recovery", "Early Buzz", "Full Alignment", "Overheated Buzz", "Full Decline"];

interface RadarSignal { label: string | null }

// 매크로 패널 — 등급·판정 없이 원자료만 (src/analyzers/macro_snapshot.py의 items 키와 동일 순서)
// 줄마다: 미국 금리 / 한국 금리·환율·변동성 / 신용·원자재 (2026-10-17 밤 real10y·kr3y·hy_spread·natgas 추가)
const MACRO_ORDER = ["us10y", "us30y", "spread_10y_2y", "real10y", "kr3y", "usdkrw", "dxy", "vix", "hy_spread", "wti", "natgas", "copper"];
interface MacroItem { value: number | null; chg_1d: number | null; chg_1w: number | null; label: string; unit: string }
interface MacroSnapshot { date: string; items: Record<string, MacroItem> }

function fmtUnit(v: number, unit: string): string {
  if (unit === "원") return `₩${Math.round(v).toLocaleString()}`;
  if (unit === "$") return `$${v.toFixed(2)}`;
  if (unit.startsWith("$/")) return `$${v.toFixed(2)}${unit.slice(1)}`;   // $/lb, $/MMBtu
  if (unit === "%p" || unit === "%") return `${v.toFixed(2)}${unit}`;
  return v.toFixed(2);
}
function fmtMacroValue(item: MacroItem): string {
  return item.value == null ? "-" : fmtUnit(item.value, item.unit);
}
function fmtMacroChg(item: MacroItem): string {
  if (item.chg_1d == null) return "-";
  const sign = item.chg_1d >= 0 ? "+" : "";
  const digits = item.unit === "원" ? 1 : 2;
  return `${sign}${item.chg_1d.toFixed(digits)}`;
}

// 주간 브리핑(scripts/generate_weekly_briefing.py)에서 쓰는 칸만
type Ref = { market: string; symbol: string; name?: string | null };
type Tagged = Ref & { tags: string[] };
interface WeekBrief {
  week: string;
  us?: { index_chg_1w: number | null };
  kr?: { index_chg_1w: number | null };
  regime?: Partial<Record<Mkt, { combos: { name: string }[] }>> | null;
  watchlist?: { added: Ref[]; added_count?: number; has_prev: boolean; total: number } | null;
  sentiment_heating?: (Ref & { path?: string })[];
  turnaround?: { total: number; by_market: Record<string, number>; has_prev: boolean; added: Ref[]; added_count: number } | null;
  earnings_week?: { total: number; by_market: Record<string, number>; items: (Tagged & { date: string; estimate: boolean })[] } | null;
  kr_disclosures?: { contract: { count: number; items: (Tagged & { pct?: number | null })[] }; prelim: { count: number; items: Tagged[] };
                     termination?: { count: number; items: Tagged[] }; amend?: { count: number; items: Tagged[] } } | null;
  insider_week?: { by_market: Record<string, number>; items: (Tagged & { all_plan?: boolean })[]; discovery?: (Tagged & { all_plan?: boolean })[];
                   split_by_market?: Record<string, { tagged: number; discovery: number }> } | null;
  us_8k_week?: { items: (Tagged & { warn: boolean })[] } | null;
  week_focus?: {
    themes: { market: Mkt; theme_id: string; name: string; label: string | null; why: string }[];
    stocks: (Ref & { reasons: string[]; theme: string })[];
    stock_total: Record<string, number>;
  } | null;
}

type Mkt = "US" | "KR";
const MKT_NAME: Record<Mkt, { flag: string; name: string; sub: string }> = {
  US: { flag: "🇺🇸", name: "미국", sub: "S&P 500·400" },
  KR: { flag: "🇰🇷", name: "한국", sub: "시총 3000억+" },
};
const nameOf = (x: Ref) => x.market === "KR" ? (x.name && x.name !== x.symbol ? x.name : krStockName(x.symbol)) : x.symbol;
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const sgn = (v?: number | null) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`);

// 이름 줄(2026-11-15, 사용자: "개요는 좀 단순하다") - 예전엔 숫자 타일이라 "실적 반전 7"을 보고 다시 눌러 들어가야 했다.
// 이번 주 바뀐 이름을 그대로 적는다. 순서는 브리핑에 담긴 순서 그대로 - 점수·순위 아님.
const SHOW = 6;
function NameLine({ label, items, total, href, empty, extra, warn }: {
  label: string; items: (Ref & { extra?: string })[]; total?: number; href: string; empty?: string; extra?: ReactNode; warn?: boolean;
}) {
  const more = (total ?? items.length) - Math.min(items.length, SHOW);
  if (items.length === 0 && !empty) return null;
  return (
    <div className="flex gap-3 py-1.5 text-[13.5px] leading-relaxed" style={{ borderTop: "1px solid var(--border)" }}>
      <a href={href} className="w-[7.5rem] shrink-0 hover:underline" style={{ color: warn ? "#f87171" : "var(--text-muted)" }}>{label}</a>
      <p className="min-w-0 flex-1" style={{ color: "var(--text-secondary)" }}>
        {items.length === 0 ? <span style={{ color: "var(--text-faint)" }}>{empty}</span> : items.slice(0, SHOW).map((x, i) => (
          <span key={`${x.market}:${x.symbol}`}>
            {i > 0 && <span style={{ color: "var(--text-faint)" }}> · </span>}
            <StockLink market={x.market} symbol={x.symbol} className="font-semibold" style={{ color: "var(--text-primary)" }}>{nameOf(x)}</StockLink>
            {x.extra && <span className="text-[12px]" style={{ color: "var(--text-muted)" }}> {x.extra}</span>}
          </span>
        ))}
        {more > 0 && <a href={href} className="hover:underline" style={{ color: "var(--text-muted)" }}> 외 {more}</a>}
        {extra}
      </p>
    </div>
  );
}

// 유명 투자자 13F 요약(미국 단락만, 2026-10-25) - /api/investors 값 그대로
type Inst13f = { period: string; filed: string; newTotal: number; shared: { ticker: string; n: number; newN: number }[]; sharedCount: number;
  conviction: number };

function MarketBlock({ m, brief, cands, radar, onRadar, inst }: {
  m: Mkt; brief: WeekBrief | null; cands: { total: number; fresh: number | null } | null;
  radar: Record<string, number> | null; onRadar: () => void; inst?: Inst13f | null;
}) {
  const wl = `/watchlist?market=${m}`;
  const of = <T extends Ref>(xs?: T[] | null) => (xs ?? []).filter((x) => (x.market ?? "KR") === m);
  const w = brief?.watchlist, ta = brief?.turnaround, ew = brief?.earnings_week, kd = brief?.kr_disclosures, ins = brief?.insider_week;
  // 브리핑엔 새로 들어온 종목을 일부만 담는다 - 잘렸으면 시장별 전체 수를 모른다. 담긴 것만 이름으로, 외 N은 담긴 범위 안에서만
  const added = of(w?.added);
  const taAdded = of(ta?.added);
  const myEarn = of(ew?.items).filter((x) => x.tags.length > 0).map((x) => ({ ...x, extra: `${md(x.date)}${x.estimate ? " 추정" : ""}` }));
  const hot = of(brief?.sentiment_heating).filter((x) => String(x.path ?? "").endsWith("HOT"));
  const insMine = of(ins?.items).filter((x) => !x.all_plan);
  const insNew = of(ins?.discovery).filter((x) => !x.all_plan);
  const bigContract = m === "KR" ? (kd?.contract.items ?? []).filter((x) => (x.pct ?? 0) >= 10).map((x) => ({ ...x, market: "KR", extra: `매출의 ${Math.round(x.pct!)}%` })) : [];
  const term = m === "KR" ? (kd?.termination?.items ?? []).map((x) => ({ ...x, market: "KR" })) : [];
  const warn8k = m === "US" ? (brief?.us_8k_week?.items ?? []).filter((x) => x.warn) : [];
  const labels = radar == null ? null : LABEL_ORDER.filter(l => radar[l]).map(l => `${LABEL_KO[l] ?? l} ${radar[l]}`);
  return (
    <Section title={<>{MKT_NAME[m].flag} {MKT_NAME[m].name}</>} sub={MKT_NAME[m].sub}
      right={brief && <span style={{ color: "var(--text-faint)" }}>{brief.week.slice(5).replace("-", "/")} 주 브리핑 기준</span>}>
      {!brief ? <p className="text-[13px]" style={{ color: "var(--text-faint)" }}>브리핑 전</p> : (
        <div>
          <NameLine label="새로 통과" items={w?.has_prev ? added : []} href={cands?.fresh ? `${wl}&new=1` : wl}
            empty={w?.has_prev ? "없음" : "비교는 다음 주부터"}
            extra={<span className="text-[12px]" style={{ color: "var(--text-faint)" }}>{added.length ? " · " : ""}재무 필터 통과 {cands ? cands.total : "-"}곳</span>} />
          <NameLine label="실적 반전 신규" items={ta?.has_prev ? taAdded : []} href={`${wl}&preset=turnaround`}
            empty={ta ? (ta.has_prev ? "없음" : "비교는 다음 주부터") : "브리핑 전"} />
          <NameLine label="내 종목 실적 발표" items={myEarn} href="/briefing#earnings"
            empty={ew ? `내 관심·노트 종목은 없음 (전체 ${ew.by_market[m] ?? 0}곳)` : "브리핑 전"} />
          <NameLine label="관심도 HOT 진입" items={hot} href="/briefing#sentiment" />
          <NameLine label="큰 공급계약" items={bigContract} href="/briefing#disclosures" />
          <NameLine label="⚠ 계약 해지" items={term} href="/briefing#disclosures" warn />
          <NameLine label="⚠ 8-K 주의" items={warn8k} href="/briefing#us8k" warn />
          <NameLine label="내부자 매수" items={insMine} href="/briefing#insider"
            empty={insNew.length ? "관심 종목은 없음" : undefined}
            extra={insNew.length > 0 ? <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>{insMine.length ? " · " : ""}관심 밖 {insNew.length}곳</span> : undefined} />
          {m === "US" && inst && (
            <div className="flex gap-3 py-1.5 text-[13.5px] leading-relaxed" style={{ borderTop: "1px solid var(--border)" }}
              title="고른 운용사 15곳이 각자 가장 최근 분기에 신규·추가 매수한 종목 중 2곳 이상이 함께 산 것. 45일 늦은 사실이고 매수 신호가 아닙니다.">
              <a href="/investors#shared" className="w-[7.5rem] shrink-0 hover:underline" style={{ color: "var(--text-muted)" }}>13F 함께 산 종목</a>
              <p className="min-w-0 flex-1" style={{ color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                {inst.shared.length === 0 ? <span style={{ color: "var(--text-faint)" }}>2곳 이상이 함께 산 종목 없음</span>
                  : inst.shared.map((t, i) => (
                    <span key={t.ticker}>{i > 0 && <span style={{ color: "var(--text-faint)" }}> · </span>}
                      <StockLink market="US" symbol={t.ticker} className="font-semibold" style={{ color: "var(--text-primary)" }}>{t.ticker}</StockLink>
                      <span className="text-[12px]" style={{ color: "var(--text-muted)" }}> {t.n}곳</span></span>
                  ))}
                <span className="text-[12px]" style={{ color: "var(--text-faint)" }}> · {quarterLabel(inst.period)} 보유</span>
              </p>
            </div>
          )}
          {/* 테마 레이더 라벨 - 누르면 그 시장으로 레이더 */}
          <div className="flex gap-3 py-1.5 text-[13.5px]" style={{ borderTop: "1px solid var(--border)" }}>
            <a href="/radar" onClick={onRadar} className="w-[7.5rem] shrink-0 hover:underline" style={{ color: "var(--text-muted)" }}>테마 라벨</a>
            <a href="/radar" onClick={onRadar} className="min-w-0 flex-1 hover:underline" style={{ color: "var(--text-secondary)" }}>
              {labels == null ? "불러오는 중…" : labels.length === 0 ? "이번 주 라벨 붙은 테마 없음" : labels.join(" · ")}
            </a>
          </div>
        </div>
      )}
      {cands?.total === 0 && (
        <p className="mt-2 text-[12px]" style={{ color: "var(--text-muted)" }}>이번 주 통과 후보가 없습니다. GitHub → Actions → Weekly Watchlist Screen 실행 여부를 확인하세요.</p>
      )}
    </Section>
  );
}

// 이번 주 한눈에(2026-11-15) - 개요 맨 위. 브리핑 🎯·회고 대기·두 시장 한 줄. 값은 최신 브리핑 그대로(새로 계산하지 않음).
function WeekGlance({ brief, due }: { brief: WeekBrief | null; due: number | null }) {
  if (!brief) return null;
  const f = brief.week_focus;
  const combo = (m: Mkt) => (brief.regime?.[m]?.combos ?? []).map((c) => c.name).join("·");
  const row = (icon: string, label: string, body: ReactNode, href?: string) => (
    <div className="flex gap-3 py-2 text-[14px] leading-relaxed" style={{ borderTop: "1px solid var(--border)" }}>
      <span className="w-[6.5rem] shrink-0 font-semibold" style={{ color: "var(--text-primary)" }}><span aria-hidden className="mr-1">{icon}</span>{label}</span>
      <div className="min-w-0 flex-1" style={{ color: "var(--text-secondary)" }}>{body}</div>
      {href && <a href={href} className="shrink-0 self-start text-[12px] hover:underline" style={{ color: "var(--text-muted)" }}>보기 →</a>}
    </div>
  );
  const more = f ? Object.values(f.stock_total ?? {}).reduce((a, b) => a + b, 0) - f.stocks.length : 0;
  return (
    <Section title="이번 주 한눈에" sub={`${brief.week.slice(5).replace("-", "/")} 주 브리핑 기준 - 추천이 아니라 먼저 들여다볼 곳`}>
      {row("🌐", "시장", (["US", "KR"] as Mkt[]).map((m, i) => (
        <span key={m}>{i > 0 && <span style={{ color: "var(--text-faint)" }}> · </span>}
          {m === "US" ? "🇺🇸 S&P 500" : "🇰🇷 KOSPI"} <b style={{ color: "var(--text-primary)", fontVariantNumeric: "tabular-nums" }}>{sgn(brief[m === "US" ? "us" : "kr"]?.index_chg_1w)}</b>
          {combo(m) && <span style={{ color: "var(--text-muted)" }}> ({combo(m)})</span>}
        </span>
      )), "#regime")}
      {row("🎯", "볼 테마", !f ? <span style={{ color: "var(--text-faint)" }}>다음 브리핑(월요일 아침)부터 표시</span>
        : f.themes.length === 0 ? <span style={{ color: "var(--text-faint)" }}>이번 주 라벨 붙은 테마 없음</span>
        : f.themes.map((t, i) => (
          <span key={`${t.market}:${t.theme_id}`}>{i > 0 && <span style={{ color: "var(--text-faint)" }}> · </span>}
            <a href={`/radar/theme?id=${encodeURIComponent(t.theme_id)}&market=${t.market}#candidates`} className="hover:underline">
              {MKT_NAME[t.market].flag} <b style={{ color: "var(--text-primary)" }}>{t.name}</b>
              <span className="text-[12px]" style={{ color: "var(--text-muted)" }}> {t.label ? (LABEL_KO[t.label] ?? t.label) : "실적 먼저"}</span>
            </a>
          </span>
        )), f ? "/briefing#focus" : undefined)}
      {f && f.stocks.length > 0 && row("⭐", "볼 후보", <>
        {f.stocks.map((x, i) => (
          <span key={`${x.market}:${x.symbol}`}>{i > 0 && <span style={{ color: "var(--text-faint)" }}> · </span>}
            <StockLink market={x.market} symbol={x.symbol} className="font-semibold" style={{ color: "var(--text-primary)" }}>{nameOf(x)}</StockLink>
            <span className="text-[12px]" style={{ color: "var(--text-muted)" }}> {x.reasons.join("·")}</span>
          </span>
        ))}
        {more > 0 && <a href="/watchlist" className="hover:underline" style={{ color: "var(--text-muted)" }}> 외 {more}곳</a>}
      </>, "/briefing#focus")}
      {row("🔁", "회고", due == null ? "…" : due > 0
        ? <span><b style={{ color: "var(--accent)" }}>판단 남길 회고 {due}건</b> - 브리핑에서 맞았다·틀렸다·애매 하나만 누르면 됩니다</span>
        : <span style={{ color: "var(--text-faint)" }}>도착한 회고 없음</span>, due ? "/briefing#reviews" : "/notes")}
    </Section>
  );
}

export default function HomePage() {
  const { setMarket } = useMarket();
  const [cands, setCands] = useState<Record<Mkt, { total: number; fresh: number | null } | null>>({ US: null, KR: null });
  // 최신 주간 브리핑 - "이번 주 변화" 칸의 숫자는 전부 여기서 그대로 가져온다(2026-10-20)
  const [brief, setBrief] = useState<WeekBrief | null>(null);
  const [radar, setRadar] = useState<Record<Mkt, Record<string, number> | null>>({ US: null, KR: null });
  const [macro, setMacro] = useState<MacroSnapshot | null>(null);
  // 일별 종가 1년치(2026-10-17) - 없으면 카드는 값만(추세선·범위 없이)
  const [macroHist, setMacroHist] = useState<Record<string, Point[]>>({});
  const [openMacro, setOpenMacro] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [inst, setInst] = useState<Inst13f | null>(null);
  const [regime, setRegime] = useState<RegimeData | null>(null);   // 시장 환경 축(2026-11-07)
  const [due, setDue] = useState<number | null>(null);   // 회고 대기 - 브리핑 '회고 판정'과 같은 기준(obsStatus due)

  useEffect(() => {
    const markets: Mkt[] = ["US", "KR"];
    const candReq = markets.map((m) => fetch(`/api/watchlist/candidates?market=${m}`).then(r => r.json())
      .then(d => {
        const cs: { is_new?: boolean | null }[] = d?.candidates ?? [];
        return { total: cs.length, fresh: cs.some(c => c.is_new != null) ? cs.filter(c => c.is_new === true).length : null };
      }).catch(() => ({ total: 0, fresh: null })));
    Promise.all(candReq).then(([us, kr]) => { setCands({ US: us, KR: kr }); setLoaded(true); });
    const radarReq = markets.map((m) => fetch(`/api/radar?market=${m}`).then(r => r.json())
      .then(d => {
        const counts: Record<string, number> = {};
        (d?.signals ?? []).forEach((s: RadarSignal) => { if (s.label) counts[s.label] = (counts[s.label] ?? 0) + 1; });
        return counts;
      }).catch(() => ({} as Record<string, number>)));
    Promise.all(radarReq).then(([us, kr]) => setRadar({ US: us, KR: kr }));
    fetch("/api/investors?summary=1").then(r => r.json())
      .then(d => {
        const ms: { period: string; filed_on: string; counts: { new: number } }[] = Array.isArray(d?.managers) ? d.managers : [];
        if (!ms.length) return setInst(null);
        const sh: { ticker: string; buyers: { status: string }[] }[] = Array.isArray(d?.shared) ? d.shared : [];
        setInst({ period: ms.reduce((p, x) => (x.period > p ? x.period : p), ""), filed: ms.reduce((p, x) => (x.filed_on > p ? x.filed_on : p), ""),
          newTotal: ms.reduce((n, x) => n + (x.counts?.new ?? 0), 0),
          shared: sh.slice(0, 5).map(t => ({ ticker: t.ticker, n: t.buyers.length, newN: t.buyers.filter(b => b.status === "new").length })),
          sharedCount: sh.length, conviction: Array.isArray(d?.conviction) ? d.conviction.length : 0 });
      }).catch(() => setInst(null));
    // 매크로는 두 시장에 걸치는 배경 정보라 한 번만
    fetch("/api/data/macro")
      .then(r => r.json())
      // API가 { error }를 돌려주면(DB 오류 등) items가 없어 화면 전체가 깨졌다 - 모양이 맞을 때만 쓴다(2026-10-04).
      .then(d => setMacro(d && d.items ? d : null))
      .catch(() => setMacro(null));
    fetch("/api/notes").then(r => r.json())
      .then(d => setDue((Array.isArray(d?.observations) ? d.observations : []).filter((o: ObservationT) => obsStatus(o) === "due").length))
      .catch(() => setDue(0));
    fetch("/api/briefing")
      .then(r => r.json())
      .then(d => setBrief(Array.isArray(d?.briefings) && d.briefings.length ? d.briefings[0] : null))
      .catch(() => setBrief(null));
    fetch("/api/market-regime")
      .then(r => r.json())
      .then(d => setRegime(d && (d.US?.length || d.KR?.length) ? d : null))
      .catch(() => setRegime(null));
    fetch("/api/data/macro/history")
      .then(r => r.json())
      .then(d => setMacroHist(d && typeof d === "object" && !Array.isArray(d) ? d : {}))
      .catch(() => setMacroHist({}));
  }, []);

  // 브리핑의 "개요에서 자세히"(/#regime) - 시장 환경 칸은 데이터가 온 뒤에 생겨서 브라우저 기본 이동이 놓친다(2026-11-07)
  useEffect(() => {
    if (regime && loaded && typeof window !== "undefined" && window.location.hash === "#regime")
      document.getElementById("regime")?.scrollIntoView({ block: "start" });
  }, [regime, loaded]);

  if (!loaded) return (
    <div className="space-y-3">
      <div className="h-32 rounded-xl animate-pulse" style={{ background: "#111009" }} />
    </div>
  );

  return (
    <div className="space-y-3">
      {/* 공통 머리말 - 시장 탭 없이 한 장(2026-10-25). 맨 위 '이번 주 한눈에', 시장별 이름 줄, 그 아래 시장 환경·매크로(2026-11-15) */}
      <PageHeader title="이번 주 물밑 흐름" intro="home"
        desc="미국·한국 두 시장에서 이번 주 바뀐 것을 이름으로. 이름을 누르면 기업 카드, 줄 제목을 누르면 해당 목록 - 순위나 추천이 아닙니다." />
      {/* 첫 방문 안내 - 닫으면 이 브라우저에서는 안 보인다(2026-10-23) */}
      <WelcomePanel />

      <WeekGlance brief={brief} due={due} />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {(["US", "KR"] as Mkt[]).map((m) => (
          <MarketBlock key={m} m={m} brief={brief} cands={cands[m]} radar={radar[m]} onRadar={() => setMarket(m)} inst={inst} />
        ))}
      </div>

      {/* 시장 환경 - 축별 수준·방향 + 정해진 조합 이름(2026-11-07, 레짐 모듈). 매주 일요일 계산 */}
      {regime && (
        <Section id="regime" title="시장 환경" info="금리·신용·달러/환율·변동성·외국인 수급을 축마다 따로, 각 지표 자신의 지난 1년과 비교합니다. 정해진 조합에만 이름을 붙이고 점수·매수 판단은 없습니다."
          right={<AsOf date={regime.US?.[regime.US.length - 1]?.as_of ?? regime.KR?.[regime.KR.length - 1]?.as_of} cadence="매주 일요일" staleDays={9} />}>
          <MarketRegime data={regime} />
          <SectorTurnLine />
        </Section>
      )}

      {/* 매크로 패널 — 매일 갱신, 등급·판정 없이 원자료만 (US/KR 공통 배경 정보) */}
      {macro && (
        <Section title="매크로 지표" info="시장 전체의 배경 지표를 판단 없이 숫자 그대로 보여줍니다. 등급·추천이 아니며, 매일 갱신됩니다."
          right={<AsOf date={macro.date} cadence="매일 아침" staleDays={4} />}>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {MACRO_ORDER.map((key) => {
              const item = macro.items[key];
              if (!item) return null;
              const chg = item.chg_1d;
              const chgColor = chg == null ? "var(--text-faint)" : chg > 0 ? "#4ade80" : chg < 0 ? "#f87171" : "var(--text-muted)";
              const hist = macroHist[key] ?? [];
              const open = openMacro === key;
              return (
                <button key={key} type="button" onClick={() => setOpenMacro(open ? null : key)}
                  className="rounded-lg p-2.5 text-left transition-colors"
                  style={{ background: "var(--bg-inset)", border: `1px solid ${open ? "var(--border-ctrl)" : "transparent"}` }}
                  aria-expanded={open}>
                  <p className="text-[12px] truncate" style={{ color: "var(--text-muted)" }}>{item.label}</p>
                  <p className="text-[16px] font-bold mt-0.5" style={{ color: "var(--text-primary)", fontVariantNumeric: "tabular-nums" }}>
                    {fmtMacroValue(item)}
                  </p>
                  <p className="text-[12px] mt-0.5" style={{ color: chgColor, fontVariantNumeric: "tabular-nums" }}>
                    {fmtMacroChg(item)} <span style={{ color: "var(--text-faint)" }}>(1일)</span>
                  </p>
                  {hist.length > 1 && (
                    <>
                      <div className="mt-1.5"><Sparkline points={lastN(hist, 63)} /></div>
                      <RangeBar points={lastN(hist, 260)} fmt={(v) => fmtUnit(v, item.unit)} />
                    </>
                  )}
                </button>
              );
            })}
          </div>
          {openMacro && macro.items[openMacro] && (
            <div className="mt-2 rounded-lg p-3" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
              <BigChart key={openMacro} points={macroHist[openMacro] ?? []} title={macro.items[openMacro].label}
                fmt={(v) => fmtUnit(v, macro.items[openMacro].unit)} />
            </div>
          )}
          {Object.keys(macroHist).length > 0 && (
            <p className="text-[12px] mt-2" style={{ color: "var(--text-faint)" }}>
              작은 선은 최근 3개월, 막대는 1년 최저~최고 안에서 지금 위치(판정 아님) · 카드를 누르면 큰 그래프
            </p>
          )}
        </Section>
      )}
    </div>
  );
}
