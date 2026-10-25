"use client";

import { useEffect, useState } from "react";
import InfoTooltip from "@/src/components/InfoTooltip";
import { useMarket } from "@/src/contexts/MarketContext";
import StockLink from "@/src/components/StockLink";
import { themeName } from "@/src/lib/themeNames";
import PageHeader from "@/src/components/PageHeader";
import EmptyState from "@/src/components/EmptyState";
import { Section } from "@/src/components/Section";
import Note from "@/src/components/Note";

// scripts/compute_pick_returns.py의 HORIZONS와 반드시 일치해야 함.
const HORIZONS = [30, 60, 90, 180, 365, 730] as const;
const HORIZON_LABEL: Record<number, string> = {
  30: "30일", 60: "60일", 90: "90일", 180: "6개월", 365: "1년", 730: "2년",
};

type Bucket = Record<string, number | null> & { n: number };

type ScorecardData = {
  market: string;
  comparison: { benchmark: Bucket; filtered_equal_weight: Bucket };
  by_piotroski: Record<string, Bucket>;
  total_picks: number;
  earliest_date: string | null;
  latest_date: string | null;
};

function pct(v: number | null): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
}

function pctColor(v: number | null): string {
  if (v == null) return "var(--text-faint)";
  return v >= 0 ? "#4ade80" : "#f87171";
}


// ── 신호 사후 확인(2026-10-21) ─────────────────────────────────────────────
// 브리핑·테마 레이더가 보여준 신호가 4주·12주 뒤 지수보다 어땠는지. 분포(건수·중앙값·사분위)만 - 적중률·점수 없음(원칙 1).
type Dist = { n: number; median: number | null; q1: number | null; q3: number | null };
type SignalGroup = { key: string; label: string; desc: string; expect?: "down" | null; logged: number; backfilled: number; weeks: number;
  horizons: Record<string, Dist>; horizons_univ?: Record<string, Dist> };
type SignalRecent = { week: string; kind: string; symbol: string; backfilled: boolean; watched: boolean | null;
  ret_28d: number | null; ex_28d: number | null; ex_84d: number | null; exu_28d?: number | null; exu_84d?: number | null };
type SignalData = { first_week: string | null; last_week: string | null; groups: SignalGroup[]; recent: SignalRecent[] };
const KIND_KO: Record<string, string> = { insider_buy: "내부자 매수", turnaround_new: "실적 반전 새로", theme_busier: "테마 공시 많음",
  kr_contract_big: "큰 공급계약", kr_termination: "계약 해지", us_8k_contract: "8-K 중요 계약", us_8k_warn: "8-K 주의", sentiment_heating: "관심도 상승" };
// 기대 방향이 하락인 신호 - 초과수익이 마이너스여야 신호가 맞은 쪽
const ExpectDown = ({ g }: { g: SignalGroup }) => g.expect === "down"
  ? <span className="ml-1 text-[10px] px-1 rounded" style={{ color: "#f87171", border: "1px solid #f8717155" }} title="나쁜 소식 신호 - 초과수익이 마이너스면 신호가 맞은 쪽">기대: 하락</span>
  : null;

function SignalSection({ market }: { market: string }) {
  const [d, setD] = useState<SignalData | null>(null);
  // 비교 기준 - 기본은 유니버스 중앙값(신호 종목이 대부분 중소형주라 지수와만 비교하면 중소형주 효과가 섞인다, 2026-10-21)
  const [base, setBase] = useState<"univ" | "index">("univ");
  useEffect(() => {
    setD(null);
    const empty: SignalData = { first_week: null, last_week: null, groups: [], recent: [] };
    // 응답 모양이 다르면(배포 중·오류) 빈 값으로 - 예전엔 groups가 없으면 성적표 화면 전체가 하얗게 죽었다(2026-10-21 외형 점검)
    fetch(`/api/data/signals?market=${market}`).then((r) => r.json())
      .then((x) => setD(x && Array.isArray(x.groups) && Array.isArray(x.recent) ? x : empty)).catch(() => setD(empty));
  }, [market]);
  const indexName = market === "KR" ? "KOSPI" : "SPY";
  const univName = market === "KR" ? "한국 유니버스(시총 3000억+)" : "S&P 500·400";
  const hz = (g: SignalGroup) => (base === "univ" ? g.horizons_univ : g.horizons) ?? {};
  const cell = (x: Dist | undefined) => !x || x.n === 0
    ? <span style={{ color: "var(--text-faint)" }}>—</span>
    : <span title={`사분위 ${pct(x.q1)} ~ ${pct(x.q3)}`}>
        <b style={{ color: pctColor(x.median) }}>{pct(x.median)}</b>
        <span className="text-[11px]" style={{ color: "var(--text-faint)" }}> ({pct(x.q1)}~{pct(x.q3)}) n={x.n}</span>
      </span>;
  return (
    <Section title="신호 사후 확인"
      info="브리핑·테마 레이더가 보여준 신호를 그 주에 그대로 적어 두고, 4주·12주 뒤 수익률에서 같은 기간 지수 수익률을 뺀 값(초과수익)의 분포를 봅니다. 중앙값과 사분위(가운데 절반이 놓인 범위)만 - 신호를 더하거나 뺄 근거로 쓰는 기록이지 점수가 아닙니다.">
      <p className="text-[12px] mb-2" style={{ color: "var(--text-muted)" }}>
        {d?.first_week ? `${d.first_week} ~ ${d.last_week} 주 신호 · 시작가는 신호 주 월요일 이후 첫 거래일 종가 · ${base === "univ" ? `${univName} 전체 종목 같은 기간 수익률 중앙값` : indexName} 대비 초과수익 중앙값 (사분위)`
          : d ? "아직 적힌 신호가 없습니다 - 매주 일요일 성적표 배치 때 적고, 4주가 지나면 결과가 채워집니다." : "불러오는 중…"}
      </p>
      {d && d.groups.length > 0 && (
        <div className="flex items-center gap-1.5 mb-2 text-[11px]">
          <span style={{ color: "var(--text-muted)" }}>비교 기준</span>
          {([["univ", "유니버스 중앙값"], ["index", indexName]] as const).map(([k, label]) => (
            <button key={k} onClick={() => setBase(k)} className="px-2 py-0.5 rounded font-semibold"
              style={{ border: "1px solid var(--border)", background: base === k ? "#ffb02022" : "transparent", color: base === k ? "#ffb020" : "var(--text-faint)" }}>
              {label}
            </button>
          ))}
          <InfoTooltip content="유니버스 중앙값: 같은 유니버스 전체 종목의 같은 기간 수익률 중앙값과 비교합니다. 신호 종목은 대부분 중소형주라, 대형주 비중이 큰 지수와만 비교하면 그 기간 중소형주가 강했는지 약했는지가 섞입니다. 신호 자체의 차이를 보려면 유니버스 기준이 맞습니다." />
        </div>
      )}
      {d && d.groups.length > 0 && (
        <div className="sm:hidden space-y-1.5">
          {d.groups.map((g) => (
            <div key={g.key} className="rounded-lg px-2.5 py-2" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
              <div className="text-[13px] font-semibold" style={{ color: "var(--text-primary)" }}>{g.label}<ExpectDown g={g} /></div>
              <div className="text-[11px]" style={{ color: "var(--text-faint)" }}>{g.desc}</div>
              <div className="mt-1 text-[12px] space-y-0.5">
                <div><span style={{ color: "var(--text-muted)" }}>4주 후 초과 </span>{cell(hz(g)["28"])}</div>
                <div><span style={{ color: "var(--text-muted)" }}>12주 후 초과 </span>{cell(hz(g)["84"])}</div>
                <div style={{ color: "var(--text-faint)" }}>적힌 신호 {g.logged}건 · {g.weeks}주{g.backfilled > 0 ? ` · 소급 ${g.backfilled}` : ""}</div>
              </div>
            </div>
          ))}
        </div>
      )}
      {d && d.groups.length > 0 && (
        <div className="hidden sm:block overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr style={{ color: "var(--text-muted)" }}>
                <th className="text-left py-1.5 font-semibold">신호</th>
                <th className="text-right py-1.5 font-semibold whitespace-nowrap">4주 후 초과</th>
                <th className="text-right py-1.5 font-semibold whitespace-nowrap">12주 후 초과</th>
                <th className="text-right py-1.5 font-semibold whitespace-nowrap">적힌 신호</th>
              </tr>
            </thead>
            <tbody>
              {d.groups.map((g) => (
                <tr key={g.key} style={{ borderTop: "1px solid var(--border)" }}>
                  <td className="py-2 pr-3">
                    <div className="font-semibold" style={{ color: "var(--text-primary)" }}>{g.label}<ExpectDown g={g} /></div>
                    <div className="text-[11px]" style={{ color: "var(--text-faint)" }}>{g.desc}</div>
                  </td>
                  <td className="text-right whitespace-nowrap">{cell(hz(g)["28"])}</td>
                  <td className="text-right whitespace-nowrap">{cell(hz(g)["84"])}</td>
                  <td className="text-right text-[12px] whitespace-nowrap" style={{ color: "var(--text-faint)" }}>
                    {g.logged}건 · {g.weeks}주{g.backfilled > 0 && <div>소급 {g.backfilled}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {d && d.recent.length > 0 && (
        <details className="mt-2">
          <summary className="text-[12px] cursor-pointer" style={{ color: "var(--text-muted)" }}>4주 결과가 나온 신호 {d.recent.length}건 보기</summary>
          <div className="mt-1.5 space-y-0.5">
            {d.recent.map((r) => (
              <div key={`${r.week}-${r.kind}-${r.symbol}`} className="flex flex-wrap gap-x-2 text-[12px]">
                <span style={{ color: "var(--text-faint)" }}>{r.week.slice(5)}</span>
                <span style={{ color: "var(--text-muted)" }}>{KIND_KO[r.kind] ?? r.kind}{r.watched === false ? "·관심 밖" : ""}</span>
                {r.kind === "theme_busier"
                  ? <span style={{ color: "var(--text-primary)" }}>{themeName(r.symbol).ko}</span>
                  : <StockLink market={market} symbol={r.symbol} className="font-bold" style={{ color: "var(--text-primary)" }}>{r.symbol}</StockLink>}
                <span>4주 {pct(r.ret_28d)}</span>
                {(() => { const e4 = base === "univ" ? r.exu_28d ?? null : r.ex_28d, e12 = base === "univ" ? r.exu_84d ?? null : r.ex_84d;
                  return <>
                    <span style={{ color: pctColor(e4) }}>초과 {pct(e4)}</span>
                    {e12 != null && <span style={{ color: pctColor(e12) }}>12주 초과 {pct(e12)}</span>}
                  </>; })()}
                {r.backfilled && <span style={{ color: "var(--text-faint)" }}>소급</span>}
              </div>
            ))}
          </div>
        </details>
      )}
      <Note label="읽는 법">소급 = 기록을 시작하기 전 주를 나중에 원본 표에서 다시 만든 것(관심 표시·테마 소속은 지금 기준). 표본이 적은 동안은 숫자보다 방향만 참고하세요.
        묶음이 많아 우연히 좋거나 나빠 보이는 묶음이 생길 수 있습니다.</Note>
    </Section>
  );
}

export default function ScorecardPage() {
  const { market } = useMarket();
  const [data, setData] = useState<ScorecardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 등급별/게이트별 카드는 기간 하나를 골라서 보여준다 — 장기 투자 검증이 핵심이라 1년을 기본값으로.
  const [breakdownHorizon, setBreakdownHorizon] = useState<number>(365);

  useEffect(() => {
    setData(null);
    setError(null);
    fetch(`/api/data/scorecard?market=${market}`)
      .then((r) => r.json())
      .then((d) => {
        // API가 { error } 형태(테이블 없음·Turso 오류 등)를 반환할 수도 있으므로
        // comparison 필드 존재로 실제 데이터인지 확인 후에만 렌더링한다.
        if (d && d.comparison) setData(d);
        else setError(typeof d?.error === "string" ? d.error : "데이터를 불러오지 못했습니다.");
      })
      .catch(() => setError("데이터를 불러오지 못했습니다."));
  }, [market]);

  if (error) {
    return (
      <div className="space-y-2">
        <PageHeader title="성적표" intro="scorecard" desc="과거 워치리스트 후보의 수익률과, 브리핑·레이더 신호의 사후 확인." />
        <EmptyState title="아직 집계된 후보 수익률이 없습니다" hint="매주 일요일 밤 자동 집계 뒤 표시됩니다. 아래 신호 사후 확인은 따로 집계됩니다." />
        <SignalSection market={market} />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-card rounded-lg p-3 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        로딩 중…
      </div>
    );
  }

  const indexName = market === "KR" ? "KOSPI" : "SPY";
  const comparisonRows: { key: keyof ScorecardData["comparison"]; label: string; desc: string }[] = [
    { key: "benchmark", label: `${indexName} 단순 보유`, desc: "기준선" },
    { key: "filtered_equal_weight", label: "필터 통과 종목 균등매수", desc: "정량 필터가 값을 더했는가" },
  ];
  const bdCol = `fwd_${breakdownHorizon}d_ret`;

  return (
    <div className="space-y-2">
      <PageHeader title="성적표" intro="scorecard"
        asOf={<InfoTooltip content="과거 후보·신호에 실제 주가를 대조한 사후 검증입니다. 결과가 기대와 다를 수 있고, 그게 이 화면의 목적입니다." />}
        desc={data.earliest_date && data.latest_date
          ? `워치리스트 후보 ${data.earliest_date} ~ ${data.latest_date} · ${data.total_picks}개, 아래는 브리핑·레이더 신호의 사후 확인`
          : "아직 집계된 데이터가 없습니다 (매주 일요일 자동 집계)."} />

      {/* 2-way 비교 — 30일~2년까지 한 번에 (단기 30/60/90 스윙 검증, 180일 이후는 장기 펀더멘털 검증) */}
      <Section title="후보 수익률 비교" sub="통과 후보 vs 지수, 30일~2년"
        info="180일(6개월)부터는 1~3년 펀더멘털 보유 검증용입니다. 짧은 창(30~90일)은 참고용 스윙 검증입니다.">
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr style={{ color: "var(--text-muted)" }}>
                <th className="text-left py-1.5 font-semibold">비교 대상</th>
                {HORIZONS.map((h) => (
                  <th key={h} className="text-right py-1.5 font-semibold whitespace-nowrap">{HORIZON_LABEL[h]} 후</th>
                ))}
                <th className="text-right py-1.5 font-semibold">표본수</th>
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map(({ key, label, desc }) => {
                const b = data.comparison[key];
                return (
                  <tr key={key} style={{ borderTop: "1px solid var(--border)" }}>
                    <td className="py-2 pr-3">
                      <div className="font-semibold whitespace-nowrap" style={{ color: "var(--text-primary)" }}>{label}</div>
                      <div className="text-[11px]" style={{ color: "var(--text-faint)" }}>{desc}</div>
                    </td>
                    {HORIZONS.map((h) => {
                      const v = b[`fwd_${h}d_ret`];
                      return (
                        <td key={h} className="text-right font-bold" style={{ color: pctColor(v) }}>{pct(v)}</td>
                      );
                    })}
                    <td className="text-right" style={{ color: "var(--text-faint)" }}>{b.n}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>

      {/* 기간 선택 — F-Score 구간별 카드에 적용(게이트는 2026-08에 없앴다 - 문구만 남아 있던 것을 10-21 정리) */}
      {/* Piotroski 구간별 */}
      {/* 기간 선택은 이 칸 오른쪽에(2026-10-25 화면 통일 - 예전엔 따로 한 칸을 차지했다) */}
      <Section title={`F-Score 구간별 이후 ${HORIZON_LABEL[breakdownHorizon]} 수익률`}
        info="스크리닝 시점 Piotroski F-Score 구간이 실제 수익률 순서와 대응하는지 확인합니다. 점수가 높을수록 수익률도 높다면 필터가 실제로 값을 더하고 있다는 뜻입니다."
        right={<div className="flex rounded-lg overflow-hidden" style={{ border: "1px solid var(--border)" }}>
            {HORIZONS.map((h) => (
              <button
                key={h}
                onClick={() => setBreakdownHorizon(h)}
                className="px-2.5 py-1 text-[11px] font-semibold transition-colors"
                style={{
                  background: breakdownHorizon === h ? "#ffb02022" : "transparent",
                  color: breakdownHorizon === h ? "#ffb020" : "var(--text-faint)",
                }}
              >
                {HORIZON_LABEL[h]}
              </button>
            ))}
          </div>}>
        <div className="grid grid-cols-3 gap-2">
          {Object.entries(data.by_piotroski).map(([tier, b]) => (
            <div key={tier} className="rounded-lg p-2.5" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
              <p className="text-[13px] font-black" style={{ color: "var(--text-primary)" }}>{tier}</p>
              <p className="text-[16px] font-black mt-1" style={{ color: pctColor(b[bdCol]) }}>{pct(b[bdCol])}</p>
              <p className="text-[12px] mt-0.5" style={{ color: "var(--text-faint)" }}>n={b.n}</p>
            </div>
          ))}
        </div>
      </Section>

      <SignalSection market={market} />
    </div>
  );
}
