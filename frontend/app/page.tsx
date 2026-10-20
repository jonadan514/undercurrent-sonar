"use client";

import { useEffect, useState } from "react";
import InfoTooltip from "@/src/components/InfoTooltip";
import { useMarket } from "@/src/contexts/MarketContext";
import FlagIcon from "@/src/components/FlagIcon";
import { BigChart, RangeBar, Sparkline, lastN, type Point } from "@/src/components/MacroChart";
import AsOf from "@/src/components/AsOf";
import { LABEL_KO } from "@/src/lib/labelNames";

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
  insider_week?: { by_market: Record<string, number>; items: { market: string }[]; discovery?: { market: string }[]; discovery_count?: number } | null;
  observation_reviews?: unknown[];
}

function ChangeTile({ href, label, value, sub, hint }: { href: string; label: string; value: string; sub?: string; hint?: string }) {
  return (
    <a href={href} className="rounded-lg p-2.5 block transition-colors hover:brightness-125" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }} title={hint}>
      <p className="text-[11px] truncate" style={{ color: "var(--text-muted)" }}>{label}</p>
      <p className="text-[20px] font-bold leading-tight mt-0.5" style={{ color: "var(--num)", fontVariantNumeric: "tabular-nums" }}>{value}</p>
      {sub && <p className="text-[11px] mt-0.5 truncate" style={{ color: "var(--text-secondary)" }}>{sub}</p>}
    </a>
  );
}

export default function HomePage() {
  const { market } = useMarket();
  const [candidateCount, setCandidateCount] = useState<number | null>(null);
  const [newCount, setNewCount] = useState<number | null>(null);
  // 최신 주간 브리핑 - "이번 주 변화" 줄의 숫자는 전부 여기서 그대로 가져온다(2026-10-20)
  const [brief, setBrief] = useState<WeekBrief | null>(null);
  const [radarCounts, setRadarCounts] = useState<Record<string, number> | null>(null);
  const [macro, setMacro] = useState<MacroSnapshot | null>(null);
  // 일별 종가 1년치(2026-10-17) - 없으면 카드는 값만(추세선·범위 없이)
  const [macroHist, setMacroHist] = useState<Record<string, Point[]>>({});
  const [openMacro, setOpenMacro] = useState<string | null>(null);

  useEffect(() => {
    setCandidateCount(null);
    fetch(`/api/watchlist/candidates?market=${market}`)
      .then(r => r.json())
      .then(d => {
        const cs: { is_new?: boolean | null }[] = d?.candidates ?? [];
        setCandidateCount(cs.length);
        setNewCount(cs.some(c => c.is_new != null) ? cs.filter(c => c.is_new === true).length : null);
      })
      .catch(() => setCandidateCount(0));
  }, [market]);

  // Phase B에서 한국도 지원 - 선택된 시장의 라벨 요약을 보여준다.
  useEffect(() => {
    setRadarCounts(null);
    fetch(`/api/radar?market=${market}`)
      .then(r => r.json())
      .then(d => {
        const counts: Record<string, number> = {};
        (d?.signals ?? []).forEach((s: RadarSignal) => {
          if (s.label) counts[s.label] = (counts[s.label] ?? 0) + 1;
        });
        setRadarCounts(counts);
      })
      .catch(() => setRadarCounts({}));
  }, [market]);

  // 매크로 지표는 시장 토글과 무관하게 항상 같은 값 (US/KR 둘 다에 걸치는 배경 정보).
  useEffect(() => {
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

  const isKR = market === "KR";
  const indexName = isKR ? "KOSPI" : "S&P 500";

  if (candidateCount === null) return (
    <div className="space-y-3">
      <div className="h-32 rounded-xl animate-pulse" style={{ background: "#111009" }} />
    </div>
  );

  return (
    <div className="space-y-3">
      {/* Title */}
      <div className="flex items-center gap-3">
        <span className="text-[13px] font-bold px-2 py-0.5 rounded" style={{ background: "#262112", color: "#726b58" }}>
          <FlagIcon market={isKR ? "KR" : "US"} size={14} />{" "}{indexName}
        </span>
        <h1 className="text-xl font-bold text-white">
          {isKR ? "한국 시장 · 이번 주 물밑 흐름" : "미국 시장 · 이번 주 물밑 흐름"}
        </h1>
        <span className="rounded px-2 py-0.5 text-[13px] font-bold" style={{ background: "#ffb02022", color: "#ffb020", border: "1px solid #ffb02044" }}>
          주간 갱신
        </span>
      </div>

      {/* 이번 주 변화 - 무엇이 새로 생겼나만 모아 해당 화면으로 보낸다(2026-10-20). 숫자는 워치리스트·주간 브리핑 값 그대로. */}
      <div className="bg-card rounded-lg p-3">
        <div className="flex items-center gap-1.5 mb-2">
          <p className="stat-label" style={{ fontSize: 13 }}>이번 주 변화</p>
          <InfoTooltip content="이번 주에 새로 생긴 것만 모았습니다. 칸을 누르면 해당 목록으로 갑니다. 순위나 추천이 아닙니다." />
          {brief && <span className="ml-auto text-[11px]" style={{ color: "var(--text-faint)" }}>{brief.week.slice(5).replace("-", "/")} 주 브리핑 기준</span>}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          <ChangeTile href={newCount ? "/watchlist?new=1" : "/watchlist"} label="워치리스트 후보"
            value={`${candidateCount}`} sub={newCount != null ? `이번 주 신규 ${newCount}` : "재무 필터 통과, 순위 없음"}
            hint="재무 건전성 필터를 통과한 종목. 매수 신호가 아닙니다." />
          {(() => {
            const ta = brief?.turnaround;
            if (!ta) return <ChangeTile href="/watchlist?preset=turnaround" label="실적 반전" value="-" sub="브리핑 전" />;
            const added = ta.added.filter(a => a.market === market).length;
            return <ChangeTile href="/watchlist?preset=turnaround" label="실적 반전" value={`${ta.by_market[market] ?? 0}`}
              // 브리핑에는 새로 들어온 종목을 10개까지만 담는다 - 잘렸으면 시장별로 셀 수 없어 미·한 합계를 그대로 쓴다
              sub={!ta.has_prev ? "비교는 다음 주부터" : ta.added_count > ta.added.length ? `새로 ${ta.added_count} (미·한 합계)` : `새로 ${added}`}
              hint="매출 3년은 정체·역성장인데 최근 1년(없으면 분기)은 성장" />;
          })()}
          {(() => {
            const ew = brief?.earnings_week;
            const mine = (ew?.items ?? []).filter(x => x.market === market && x.tags.length > 0).length;
            return <ChangeTile href="/briefing#earnings" label="이번 주 실적 발표" value={ew ? `${ew.by_market[market] ?? 0}` : "-"}
              sub={ew ? `내 관심·노트·실적 반전 ${mine}` : "브리핑 전"} />;
          })()}
          {(() => {
            const kd = brief?.kr_disclosures;
            const all = kd ? [kd.contract, kd.prelim, kd.termination, kd.amend].filter(Boolean) as { count: number; items: { tags: string[] }[] }[] : [];
            const tagged = all.flatMap(k => k.items).filter(x => x.tags.length > 0).length;
            const term = kd?.termination?.count ?? 0;
            return <ChangeTile href="/briefing#disclosures" label="🇰🇷 한국 공시 (7일)" value={kd ? `${all.reduce((n, k) => n + k.count, 0)}` : "-"}
              sub={kd ? `관심 종목 ${tagged} · 공급계약 ${kd.contract.count}${term ? ` · 해지 ${term}` : ""}` : "브리핑 전"} />;
          })()}
          {(() => {
            const ins = brief?.insider_week;
            const mine = (ins?.items ?? []).filter(x => x.market === market).length;
            const fresh = (ins?.discovery ?? []).filter(x => x.market === market).length;
            return <ChangeTile href="/briefing#insider" label="내부자 장내 매수 (7일)" value={ins ? `${ins.by_market[market] ?? 0}` : "-"}
              sub={ins ? (ins.discovery ? `관심 종목 ${mine} · 관심 밖 ${fresh}` : `종목 ${ins.by_market[market] ?? 0}`) : "브리핑 전"}
              hint="임원·이사·대주주가 장내에서 직접 산 종목 수. 관심 밖은 관심 표시 없는 유니버스 종목(새 이름 찾기용)." />;
          })()}
          <ChangeTile href="/notes" label="관찰 노트 회고" value={`${brief?.observation_reviews?.length ?? 0}`}
            sub={(brief?.observation_reviews?.length ?? 0) > 0 ? "판단 남길 회고 도착" : "도착한 회고 없음"} />
        </div>
      </div>

      {candidateCount === 0 && (
        <div className="bg-card rounded-lg p-3 text-center text-base" style={{ color: "#726b58" }}>
          이번 주 통과 후보가 없습니다. GitHub → Actions → Weekly Watchlist Screen 실행 여부를 확인하세요.
        </div>
      )}

      {/* 이번 주 테마 레이더 — 뉴스/실적/주가 축이 만드는 라벨 요약 (US만) */}
      {radarCounts && (
        <a href="/radar" className="card-secondary rounded-lg block">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <p className="stat-label" style={{ fontSize: 13 }}>이번 주 테마 레이더</p>
                <InfoTooltip content="뉴스·실적·주가 세 축이 정해진 조합으로 겹칠 때만 라벨을 붙입니다. 종합 점수나 매수 추천이 아닙니다." />
              </div>
              {Object.keys(radarCounts).length === 0 ? (
                <p className="text-[13px] mt-1" style={{ color: "var(--text-secondary)" }}>
                  이번 주 라벨 부여된 테마 없음
                </p>
              ) : (
                <p className="text-[13px] mt-1 truncate" style={{ color: "var(--text-secondary)" }}>
                  {LABEL_ORDER.filter(l => radarCounts[l]).map(l => `${LABEL_KO[l] ?? l} ${radarCounts[l]}`).join(" · ")}
                </p>
              )}
            </div>
            <span className="text-[13px] shrink-0" style={{ color: "var(--text-muted)" }}>확인하기 →</span>
          </div>
        </a>
      )}

      {/* 이동 링크 */}
      <div className="grid grid-cols-2 gap-2">
        <a href="/briefing" className="bg-card rounded-lg p-3 block">
          <p className="stat-label mb-1" style={{ fontSize: 13 }}>주간 브리핑</p>
          <p className="text-[13px]" style={{ color: "var(--text-secondary)" }}>
            지난주 지수 흐름·워치리스트 변동·관심도 요약
          </p>
        </a>
        <a href="/sector" className="bg-card rounded-lg p-3 block">
          <p className="stat-label mb-1" style={{ fontSize: 13 }}>섹터 분석</p>
          <p className="text-[13px]" style={{ color: "var(--text-secondary)" }}>
            {indexName} 섹터별 상대강도
          </p>
        </a>
      </div>

      {/* 매크로 패널 — 매일 갱신, 등급·판정 없이 원자료만 (US/KR 공통 배경 정보) */}
      {macro && (
        <div className="bg-card rounded-lg p-3">
          <div className="flex items-center gap-1.5 mb-2">
            <p className="stat-label" style={{ fontSize: 13 }}>매크로 지표</p>
            <InfoTooltip content="시장 전체의 배경 지표를 판단 없이 숫자 그대로 보여줍니다. 등급·추천이 아니며, 매일 갱신됩니다." />
            <span className="ml-auto"><AsOf date={macro.date} cadence="매일 아침" staleDays={4} /></span>
          </div>
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
                  <p className="text-[11px] truncate" style={{ color: "var(--text-muted)" }}>{item.label}</p>
                  <p className="text-[16px] font-bold mt-0.5" style={{ color: "var(--text-primary)", fontVariantNumeric: "tabular-nums" }}>
                    {fmtMacroValue(item)}
                  </p>
                  <p className="text-[11px] mt-0.5" style={{ color: chgColor, fontVariantNumeric: "tabular-nums" }}>
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
            <p className="text-[11px] mt-2" style={{ color: "var(--text-faint)" }}>
              작은 선은 최근 3개월, 막대는 1년 최저~최고 안에서 지금 위치(판정 아님) · 카드를 누르면 큰 그래프
            </p>
          )}
        </div>
      )}
    </div>
  );
}
