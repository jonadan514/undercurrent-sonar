"use client";

import { useEffect, useState } from "react";
import InfoTooltip from "@/src/components/InfoTooltip";
import { useMarket } from "@/src/contexts/MarketContext";
import FlagIcon from "@/src/components/FlagIcon";
import { BigChart, RangeBar, Sparkline, lastN, type Point } from "@/src/components/MacroChart";

// radar/page.tsx의 편집 방침과 같은 순서 (SPEC §6.2) — 페이지별 상수 유지 관행.
const LABEL_ORDER = ["Quiet Strength", "Quiet Recovery", "Early Buzz", "Full Alignment", "Overheated Buzz", "Full Decline"];

interface RadarSignal { label: string | null }

// 매크로 패널 — 등급·판정 없이 원자료만 (src/analyzers/macro_snapshot.py의 items 키와 동일 순서)
const MACRO_ORDER = ["us10y", "us30y", "spread_10y_2y", "usdkrw", "vix", "dxy", "wti", "copper"];   // copper 2026-10-17
interface MacroItem { value: number | null; chg_1d: number | null; chg_1w: number | null; label: string; unit: string }
interface MacroSnapshot { date: string; items: Record<string, MacroItem> }

function fmtUnit(v: number, unit: string): string {
  if (unit === "원") return `₩${Math.round(v).toLocaleString()}`;
  if (unit === "$") return `$${v.toFixed(2)}`;
  if (unit === "$/lb") return `$${v.toFixed(2)}/lb`;
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

export default function HomePage() {
  const { market } = useMarket();
  const [candidateCount, setCandidateCount] = useState<number | null>(null);
  const [radarCounts, setRadarCounts] = useState<Record<string, number> | null>(null);
  const [macro, setMacro] = useState<MacroSnapshot | null>(null);
  // 일별 종가 1년치(2026-10-17) - 없으면 카드는 값만(추세선·범위 없이)
  const [macroHist, setMacroHist] = useState<Record<string, Point[]>>({});
  const [openMacro, setOpenMacro] = useState<string | null>(null);

  useEffect(() => {
    setCandidateCount(null);
    fetch(`/api/watchlist/candidates?market=${market}`)
      .then(r => r.json())
      .then(d => setCandidateCount((d?.candidates ?? []).length))
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

      {/* 워치리스트 후보 — 순위 없는 리스트업 (Primary) */}
      <a href="/watchlist" className="card-primary block" style={{ background: "var(--bg-raised)" }}>
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-1.5">
              <p className="stat-label" style={{ fontSize: 13 }}>이번 주 워치리스트 후보</p>
              <InfoTooltip content="재무 건전성 필터(Piotroski 등)를 통과한 종목을 순위 없이 리스트업합니다. 매수 신호가 아닙니다." />
            </div>
            <p className="text-5xl font-black mt-1" style={{ color: "#ffb020" }}>
              {candidateCount}
              <span className="text-lg font-normal ml-2" style={{ color: "var(--text-faint)" }}>개</span>
            </p>
            <p className="text-[13px] mt-1" style={{ color: "var(--text-secondary)" }}>
              재무 필터 통과, 순위 없음 — 탭해서 직접 검토
            </p>
          </div>
          <span className="text-[13px] shrink-0" style={{ color: "var(--text-muted)" }}>확인하기 →</span>
        </div>
      </a>

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
                  {LABEL_ORDER.filter(l => radarCounts[l]).map(l => `${l} ${radarCounts[l]}`).join(" · ")}
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
            <span className="ml-auto text-[11px]" style={{ color: "var(--text-faint)" }}>{macro.date} 기준</span>
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
