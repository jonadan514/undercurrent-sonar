"use client";

import WelcomePanel from "@/src/components/WelcomePanel";
import { useEffect, useState } from "react";
import { useMarket } from "@/src/contexts/MarketContext";
import { BigChart, RangeBar, Sparkline, lastN, type Point } from "@/src/components/MacroChart";
import AsOf from "@/src/components/AsOf";
import { LABEL_KO } from "@/src/lib/labelNames";
import { Section, StatTile } from "@/src/components/Section";
import PageHeader from "@/src/components/PageHeader";
import { quarterLabel } from "@/src/lib/institutions";

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
interface WeekBrief {
  week: string;
  turnaround?: { total: number; by_market: Record<string, number>; has_prev: boolean; added: { market: string }[]; added_count: number } | null;
  earnings_week?: { total: number; by_market: Record<string, number>; items: { market: string; tags: string[] }[] } | null;
  kr_disclosures?: { contract: { count: number; items: { tags: string[] }[] }; prelim: { count: number; items: { tags: string[] }[] };
                     termination?: { count: number; items: { tags: string[] }[] }; amend?: { count: number; items: { tags: string[] }[] } } | null;
  insider_week?: { by_market: Record<string, number>; items: { market: string }[]; discovery?: { market: string }[]; discovery_count?: number;
                   split_by_market?: Record<string, { tagged: number; discovery: number }> } | null;
  observation_reviews?: unknown[];
}

type Mkt = "US" | "KR";
const MKT_NAME: Record<Mkt, { flag: string; name: string; sub: string }> = {
  US: { flag: "🇺🇸", name: "미국", sub: "S&P 500·400" },
  KR: { flag: "🇰🇷", name: "한국", sub: "시총 3000억+" },
};

// 개요 한 장(2026-10-25 사용자 의견) - 예전엔 위 시장 탭으로 미국/한국을 바꿔 봐야 했는데, 매크로는 같고
// "이번 주 변화"는 칸이 몇 개뿐이라 두 시장을 한 화면에 단락으로 나란히 두고 매크로는 한 번만.
// 유명 투자자 13F 요약(미국 단락만, 2026-10-25) - /api/investors 값 그대로
type Inst13f = { period: string; filed: string; newTotal: number; shared: { ticker: string; n: number; newN: number }[]; sharedCount: number;
  conviction: number };

function MarketBlock({ m, brief, cands, radar, onRadar, inst }: {
  m: Mkt; brief: WeekBrief | null; cands: { total: number; fresh: number | null } | null;
  radar: Record<string, number> | null; onRadar: () => void; inst?: Inst13f | null;
}) {
  const ta = brief?.turnaround, ew = brief?.earnings_week, kd = brief?.kr_disclosures, ins = brief?.insider_week;
  const wl = `/watchlist?market=${m}`;
  const tiles: React.ReactNode[] = [
    <StatTile key="wl" href={cands?.fresh ? `${wl}&new=1` : wl} label="워치리스트 후보" value={cands ? cands.total : "-"}
      sub={cands?.fresh != null ? `이번 주 신규 ${cands.fresh}` : "재무 필터 통과, 순위 없음"} hint="재무 건전성 필터를 통과한 종목. 매수 신호가 아닙니다." />,
    (() => {
      if (!ta) return <StatTile key="ta" href={`${wl}&preset=turnaround`} label="실적 반전" value="-" sub="브리핑 전" />;
      const added = ta.added.filter(a => a.market === m).length;
      // 브리핑에는 새로 들어온 종목을 10개까지만 담는다 - 잘렸으면 시장별로 셀 수 없어 미·한 합계를 그대로 쓴다
      return <StatTile key="ta" href={`${wl}&preset=turnaround`} label="실적 반전" value={ta.by_market[m] ?? 0}
        sub={!ta.has_prev ? "비교는 다음 주부터" : ta.added_count > ta.added.length ? `새로 ${ta.added_count} (미·한 합계)` : `새로 ${added}`}
        hint="매출 3년은 정체·역성장인데 최근 1년(없으면 분기)은 성장" />;
    })(),
    (() => {
      const mine = (ew?.items ?? []).filter(x => x.market === m && x.tags.length > 0).length;
      return <StatTile key="ew" href="/briefing#earnings" label="이번 주 실적 발표" value={ew ? ew.by_market[m] ?? 0 : "-"}
        sub={ew ? `내 관심·노트·실적 반전 ${mine}` : "브리핑 전"} />;
    })(),
    ...(m === "KR" ? [(() => {
      const all = kd ? [kd.contract, kd.prelim, kd.termination, kd.amend].filter(Boolean) as { count: number; items: { tags: string[] }[] }[] : [];
      const tagged = all.flatMap(k => k.items).filter(x => x.tags.length > 0).length;
      const term = kd?.termination?.count ?? 0;
      return <StatTile key="kd" href="/briefing#disclosures" label="한국 공시 (7일)" value={kd ? all.reduce((n, k) => n + k.count, 0) : "-"}
        sub={kd ? `관심 종목 ${tagged} · 공급계약 ${kd.contract.count}${term ? ` · 해지 ${term}` : ""}` : "브리핑 전"} />;
    })()] : []),
    (() => {
      // 목록은 30개에서 잘린다 - 시장별 전체 수가 있으면 그것을(10/21 리뷰)
      const sp = ins?.split_by_market?.[m];
      const mine = sp ? sp.tagged : (ins?.items ?? []).filter(x => x.market === m).length;
      const fresh = sp ? sp.discovery : (ins?.discovery ?? []).filter(x => x.market === m).length;
      return <StatTile key="ins" href="/briefing#insider" label="내부자 장내 매수 (7일)" value={ins ? ins.by_market[m] ?? 0 : "-"}
        sub={ins ? (ins.discovery ? `관심 종목 ${mine} · 관심 밖 ${fresh}` : `종목 ${ins.by_market[m] ?? 0}`) : "브리핑 전"}
        hint="임원·이사·대주주가 장내에서 직접 산 종목 수. 관심 밖은 관심 표시 없는 유니버스 종목(새 이름 찾기용)." />;
    })(),
    // 유명 투자자 13F - 카드 두 칸 폭에 '여러 곳이 함께 산 종목' 상위 5개(2026-10-26 사용자 결정 - 새로 산 개수보다 겹친 이름이 의미 있다).
    // 정렬은 겹친 운용사 수 → 새로 산 곳 수 → 평가액(/api/investors 그대로), 점수·추천 아님. 미국만(13F는 미국 상장주식)
    ...(m === "US" ? [
      <a key="13f" href="/investors#shared" className="col-span-2 rounded-lg px-3 py-2.5 block transition-colors hover:brightness-125"
        style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}
        title="고른 운용사 15곳이 각자 가장 최근 분기에 새로 사거나 늘린 종목 중 2곳 이상 겹친 것. 45일 늦은 사실이고 매수 신호가 아닙니다.">
        <p className="text-[12px] truncate" style={{ color: "var(--text-muted)" }}>
          유명 투자자 13F · 여러 곳이 함께 산 종목{inst ? ` · ${quarterLabel(inst.period)} 말` : ""}
        </p>
        {!inst ? <p className="text-[13px] mt-1" style={{ color: "var(--text-faint)" }}>아직 없음</p>
          : inst.shared.length === 0 ? <p className="text-[13px] mt-1" style={{ color: "var(--text-secondary)" }}>2곳 이상 겹친 종목 없음</p> : (
          <p className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[14px]" style={{ fontVariantNumeric: "tabular-nums" }}>
            {inst.shared.map((t) => (
              <span key={t.ticker} className="whitespace-nowrap">
                <b style={{ color: "var(--num, #ffb020)" }}>{t.ticker}</b>
                <span className="text-[12px]" style={{ color: "var(--text-secondary)" }}> {t.n}곳{t.newN ? `(새로 ${t.newN})` : ""}</span>
              </span>
            ))}
          </p>
        )}
        {inst && (
          <p className="text-[12px] mt-0.5 truncate" style={{ color: "var(--text-secondary)" }}>
            {inst.sharedCount > inst.shared.length ? `외 ${inst.sharedCount - inst.shared.length}종목 · ` : ""}확신 매수(새로 샀는데 비중 3%+) {inst.conviction}
          </p>
        )}
      </a>,
    ] : []),
  ];
  const labels = radar == null ? null : LABEL_ORDER.filter(l => radar[l]).map(l => `${LABEL_KO[l] ?? l} ${radar[l]}`);
  return (
    <Section title={<>{MKT_NAME[m].flag} {MKT_NAME[m].name}</>} sub={MKT_NAME[m].sub}
      right={brief && <span style={{ color: "var(--text-faint)" }}>{brief.week.slice(5).replace("-", "/")} 주 브리핑 기준</span>}>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">{tiles}</div>
      {/* 테마 레이더 라벨 - 누르면 그 시장으로 레이더 */}
      <a href="/radar" onClick={onRadar} className="mt-2 flex items-center gap-2 rounded-lg px-3 py-2 text-[13px] hover:brightness-125"
        style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
        <span className="shrink-0 text-[12px]" style={{ color: "var(--text-muted)" }}>테마 레이더</span>
        <span className="min-w-0 truncate" style={{ color: "var(--text-secondary)" }}>
          {labels == null ? "불러오는 중…" : labels.length === 0 ? "이번 주 라벨 붙은 테마 없음" : labels.join(" · ")}
        </span>
        <span className="ml-auto shrink-0 text-[12px]" style={{ color: "var(--text-muted)" }}>보기 →</span>
      </a>
      {cands?.total === 0 && (
        <p className="mt-2 text-[12px]" style={{ color: "var(--text-muted)" }}>이번 주 통과 후보가 없습니다. GitHub → Actions → Weekly Watchlist Screen 실행 여부를 확인하세요.</p>
      )}
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
    fetch("/api/briefing")
      .then(r => r.json())
      .then(d => setBrief(Array.isArray(d?.briefings) && d.briefings.length ? d.briefings[0] : null))
      .catch(() => setBrief(null));
    fetch("/api/data/macro/history")
      .then(r => r.json())
      .then(d => setMacroHist(d && typeof d === "object" && !Array.isArray(d) ? d : {}))
      .catch(() => setMacroHist({}));
  }, []);

  if (!loaded) return (
    <div className="space-y-3">
      <div className="h-32 rounded-xl animate-pulse" style={{ background: "#111009" }} />
    </div>
  );

  const reviews = brief?.observation_reviews?.length ?? 0;
  return (
    <div className="space-y-3">
      {/* 공통 머리말 - 시장 탭 없이 한 장(2026-10-25). 시장별 숫자는 아래 두 단락, 매크로는 공통 */}
      <PageHeader title="이번 주 물밑 흐름" intro="home"
        desc="미국·한국 두 시장의 이번 주 변화를 한 장에. 숫자 칸을 누르면 그 목록으로 갑니다 - 순위나 추천이 아닙니다." />
      {/* 첫 방문 안내 - 닫으면 이 브라우저에서는 안 보인다(2026-10-23). 다른 화면처럼 제목 아래에(2026-10-25 화면 통일) */}
      <WelcomePanel />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {(["US", "KR"] as Mkt[]).map((m) => (
          <MarketBlock key={m} m={m} brief={brief} cands={cands[m]} radar={radar[m]} onRadar={() => setMarket(m)} inst={inst} />
        ))}
      </div>

      {/* 관찰 노트 회고는 시장 구분이 없다 - 공통 한 줄 */}
      <a href="/notes" className="flex items-center gap-3 rounded-xl px-4 py-3 hover:brightness-125"
        style={{ background: reviews > 0 ? "#ffb02010" : "var(--bg-card)", border: `1px solid ${reviews > 0 ? "#ffb02055" : "var(--border)"}` }}>
        <span className="text-[15px] font-bold" style={{ color: "var(--text-primary)" }}>관찰 노트 회고</span>
        <span className="text-[13px]" style={{ color: reviews > 0 ? "#ffb020" : "var(--text-muted)" }}>
          {reviews > 0 ? `판단 남길 회고 ${reviews}건 도착` : "도착한 회고 없음"}
        </span>
        <span className="ml-auto text-[12px]" style={{ color: "var(--text-muted)" }}>노트로 →</span>
      </a>

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
