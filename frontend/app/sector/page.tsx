"use client";

import { useEffect, useState } from "react";
import InfoTooltip from "@/src/components/InfoTooltip";
import { useMarket } from "@/src/contexts/MarketContext";
import FlagIcon from "@/src/components/FlagIcon";
import StockLink from "@/src/components/StockLink";
import AsOf from "@/src/components/AsOf";
import PageHeader, { IndexBadge } from "@/src/components/PageHeader";
import EmptyState from "@/src/components/EmptyState";

// 경기 사이클 판정(회복기·성장기 등)은 2026-10-20에 화면에서 뺐다 - 대표 섹터 3개씩의 1달 RS 평균 중 최댓값을
// 고르는 단일 판정이라 원칙 1(단일 판정 없음)과 어긋나고, 에너지·소재가 두 단계에 겹쳐 구분력도 약했다.
// 대신 3달·1달 상대강도 방향이 엇갈리는 섹터를 숫자 그대로 보여준다(판정이 아니라 조건 일치 목록).

const PERIOD_TABS = ["1d", "1w", "1m", "3m"] as const;
type Period = typeof PERIOD_TABS[number];

function pct(v: number | null | undefined, digits = 2) {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function RetCell({ val }: { val: number | null | undefined }) {
  if (val == null) return <td className="px-2 py-1.5 text-center" style={{ color: "var(--text-faint)" }}>—</td>;
  const color = val > 0 ? "#4ade80" : val < 0 ? "#f87171" : "var(--text-muted)";
  return (
    <td className="px-2 py-1.5 text-center font-semibold text-[12px]" style={{ color }}>
      {pct(val)}
    </td>
  );
}

export default function SectorPage() {
  const { market } = useMarket();
  const [data, setData]       = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod]   = useState<Period>("1w");
  const [openKey, setOpenKey] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setData(null);
    const url = market === "KR" ? "/api/data/kr/sector" : "/api/data/sector";
    fetch(url).then(r => r.json()).then(d => { setData(d); setLoading(false); });
  }, [market]);

  if (loading) return <p className="text-sm" style={{ color: "var(--text-muted)" }}>로딩 중…</p>;

  if (!data) return (
    <div className="space-y-2">
      <PageHeader title="섹터 분석" />
      {/* 예전 문구는 없는 작업(Daily Analysis)을 가리켰다 - 섹터는 Weekly Market Analysis(화요일 아침) */}
      <EmptyState title="섹터 분석 데이터가 없습니다"
        hint="매주 화요일 아침 자동으로 계산됩니다. 지금 만들려면 GitHub → Actions → Weekly Market Analysis → Run workflow" />
    </div>
  );

  const isKR = market === "KR";

  const rows: any[]       = isKR ? (data.sector_data ?? []) : (data.etf_data ?? []);
  const rsHistory: any[]  = data.rs_history ?? [];
  const sectorStocks: Record<string, any[]> = data.sector_stocks ?? {};
  const leading: any[]    = data.leading ?? [];
  const lagging: any[]    = data.lagging ?? [];
  const benchmarkRet      = isKR ? data.kospi_ret : data.spy_ret;

  function rowKey(row: any) { return isKR ? row.sector : row.ticker; }
  function rowLabel(row: any) { return isKR ? row.sector : row.ticker; }
  function rowSubLabel(row: any) { return isKR ? "" : row.name; }

  // 전환 중인 섹터 - 3달 상대강도와 1달 상대강도의 부호가 다른 섹터. 주간 추이에서 최근 2주가 같은 방향이면 함께 표시.
  const histByKey: Record<string, any> = Object.fromEntries(rsHistory.map((h: any) => [isKR ? h.sector : h.ticker, h]));
  const turning = (dir: "up" | "down") => rows
    .filter((r: any) => r.rs_3m != null && r.rs_1m != null && (dir === "up" ? r.rs_3m < 0 && r.rs_1m > 0 : r.rs_3m > 0 && r.rs_1m < 0))
    .sort((a: any, b: any) => dir === "up" ? b.rs_1m - a.rs_1m : a.rs_1m - b.rs_1m)
    .map((r: any) => {
      const h = histByKey[rowKey(r)];
      const twoWeeks = h && h.w0 != null && h.w1 != null && (dir === "up" ? h.w0 > 0 && h.w1 > 0 : h.w0 < 0 && h.w1 < 0);
      return { row: r, twoWeeks };
    });
  const turningUp = turning("up");
  const turningDown = turning("down");

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="flex items-center gap-x-2.5 gap-y-1 flex-wrap">
        <IndexBadge><FlagIcon market={isKR ? "KR" : "US"} size={14} />{" "}{isKR ? "KOSPI" : "S&P 500"}</IndexBadge>
        <h1 className="text-[20px] sm:text-[22px] font-bold" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>섹터 분석</h1>
        <AsOf date={data.date} cadence="매주 화요일 아침" staleDays={8} />
        {/* KR만 두 경로가 있다 - KRX가 코스피200 섹터지수를 못 내려주면(로그인 만료,
            점검 등) 대표 종목 평균으로 조용히 폴백하는데, 그 사실이 화면에 안 보이면
            "왜 이 숫자가 지난주랑 계산 기준이 다른가"를 알 방법이 없다.
            KRX_SECTOR_INDEX_JSON을 붙이기 전 캐시(sector_source 필드 자체가 없음)도
            폴백과 같은 취급 - 그때는 항상 앵커 종목으로 계산됐었다. */}
        {isKR && (
          <span
            className="text-[11px] font-semibold px-2 py-0.5 rounded"
            style={
              data.sector_source === "krx"
                ? { background: "#4ade8020", color: "#4ade80" }
                : { background: "#facc1520", color: "#facc15" }
            }
          >
            {data.sector_source === "krx" ? "KRX 공식 지수" : "대표 종목 기준 (폴백)"}
          </span>
        )}
        <InfoTooltip content={isKR
          ? "코스피200 섹터지수(정보기술·금융 등) + 유틸리티 업종지수(전기·가스) 기반 상대강도 분석입니다. KRX 지수를 받지 못하면 섹터별 대표 종목 평균으로 계산합니다."
          : "11개 SPDR ETF 기반 섹터 순환 분석입니다. SPY 대비 상대 강도(RS)로 경기 사이클을 판단합니다."} />
      </div>

      {/* 전환 중인 섹터 + 선행·후행 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">

        {/* 전환 중인 섹터 - 3달과 1달 상대강도 방향이 엇갈림 */}
        <div className="bg-card rounded-xl p-3 space-y-2">
          <div className="flex items-center gap-1.5">
            <p className="text-[14px] font-bold text-white">전환 중인 섹터</p>
            <InfoTooltip content={`3달 상대강도와 1달 상대강도의 방향이 다른 섹터입니다. 3달은 시장(${isKR ? "KOSPI" : "SPY"})보다 약했는데 최근 1달은 강하면 '돌아서는 중', 그 반대면 '꺾이는 중'. 주간 추이에서 최근 2주가 같은 방향이면 함께 표시합니다. 판정이 아니라 조건에 맞는 섹터 목록입니다.`} />
          </div>
          {([["up", "↗ 돌아서는 중", "3달 약세 → 최근 1달 강세", turningUp, "#4ade80"],
             ["down", "↘ 꺾이는 중", "3달 강세 → 최근 1달 약세", turningDown, "#f87171"]] as const).map(([k, title, sub, list, color]) => (
            <div key={k}>
              <p className="text-[12px] font-bold" style={{ color }}>{title} <span className="font-normal text-[11px]" style={{ color: "var(--text-faint)" }}>{sub}</span></p>
              {list.length === 0 ? (
                <p className="text-[12px] mt-0.5" style={{ color: "var(--text-muted)" }}>없음</p>
              ) : (
                <div className="mt-1 space-y-1">
                  {list.map(({ row, twoWeeks }) => (
                    <div key={rowKey(row)} className="flex items-center gap-2 flex-wrap text-[12px]">
                      <span className="font-bold text-white">{rowLabel(row)}</span>
                      {rowSubLabel(row) && <span style={{ color: "var(--text-muted)" }}>{rowSubLabel(row)}</span>}
                      <span style={{ color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                        3달 {pct(row.rs_3m)} → 1달 {pct(row.rs_1m)}
                      </span>
                      {twoWeeks && (
                        <span className="text-[11px] px-1.5 rounded" style={{ background: color + "18", color }}>
                          최근 2주 연속 {k === "up" ? "+" : "−"}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* 선행 / 후행 섹터 */}
        <div className="bg-card rounded-xl p-3 space-y-2">
          <div>
            <div className="flex items-center gap-1.5 mb-1">
              <p className="text-[13px] font-bold" style={{ color: "#ffb020" }}>↑ 선행 섹터</p>
              <InfoTooltip content="최근 1개월 시장 대비 상대강도(RS)가 가장 높은 상위 3개 섹터입니다. 최근 시장보다 상대적으로 강했다는 뜻입니다." />
            </div>
            <div className="flex flex-wrap gap-1">
              {leading.map((l: any, i: number) => (
                <span key={isKR ? (l.sector ?? i) : (l.ticker ?? i)} className="text-[12px] font-bold px-2 py-0.5 rounded-lg"
                  style={{ background: "#ffb02018", color: "#ffb020", border: "1px solid #ffb02033" }}>
                  {isKR ? l.sector : `${l.ticker} · ${l.name}`}
                </span>
              ))}
              {leading.length === 0 && <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>없음</p>}
            </div>
          </div>
          <div>
            <div className="flex items-center gap-1.5 mb-1">
              <p className="text-[13px] font-bold" style={{ color: "#f87171" }}>↓ 후행 섹터</p>
              <InfoTooltip content="최근 1개월 시장 대비 상대강도(RS)가 가장 낮은 하위 3개 섹터입니다(음수만). 최근 시장보다 상대적으로 약했다는 뜻입니다." />
            </div>
            <div className="flex flex-wrap gap-1">
              {lagging.map((l: any, i: number) => (
                <span key={isKR ? (l.sector ?? i) : (l.ticker ?? i)} className="text-[12px] font-bold px-2 py-0.5 rounded-lg"
                  style={{ background: "#f8717118", color: "#f87171", border: "1px solid #f8717133" }}>
                  {isKR ? l.sector : `${l.ticker} · ${l.name}`}
                </span>
              ))}
              {lagging.length === 0 && <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>없음</p>}
            </div>
          </div>
        </div>
      </div>

      {/* RS History */}
      <div className="bg-card rounded-xl overflow-hidden">
        <div className="px-3 py-2 flex items-center gap-2" style={{ borderBottom: "1px solid var(--border)" }}>
          <p className="text-[14px] font-bold text-white">주간 상대강도 추이 <span className="text-[12px] font-normal" style={{ color: "var(--text-muted)" }}>(최근 4주)</span></p>
          <InfoTooltip content={`${isKR ? "KOSPI" : "SPY"} 대비 초과 수익률입니다. 양수(+)면 시장보다 더 올랐고, 음수(-)면 시장보다 덜 올랐다는 의미입니다. 여러 주에 걸쳐 양수를 유지하면 선행 섹터로 분류됩니다.`} />
        </div>
        <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              <th className="px-3 py-1.5 text-left stat-label w-36">섹터</th>
              {["이번주", "1주전", "2주전", "3주전"].map(h => (
                <th key={h} className="px-2 py-1.5 text-center stat-label">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rsHistory.map((row: any, i: number) => (
              <tr key={isKR ? (row.sector ?? i) : (row.ticker ?? i)} style={{ borderBottom: "1px solid var(--border-dim)" }}>
                <td className="px-3 py-1.5">
                  {isKR ? (
                    <span className="text-white text-[12px] font-semibold">{row.sector}</span>
                  ) : (
                    <>
                      <span className="font-bold text-white">{row.ticker}</span>
                      <span className="ml-1 text-[11px]" style={{ color: "var(--text-muted)" }}>{row.name}</span>
                    </>
                  )}
                </td>
                <RetCell val={row.w0} />
                <RetCell val={row.w1} />
                <RetCell val={row.w2} />
                <RetCell val={row.w3} />
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>

      {/* 섹터 히트맵 */}
      <div className="bg-card rounded-xl overflow-hidden">
        <div className="px-3 py-2 flex items-center gap-2" style={{ borderBottom: "1px solid var(--border)" }}>
          <p className="text-[14px] font-bold text-white">섹터별 수익률 · 상대강도</p>
          <InfoTooltip content="왼쪽 수치(%)는 해당 기간 절대 수익률, 오른쪽 바와 수치는 시장(SPY/KOSPI) 대비 상대강도(RS)입니다. RS가 양수이면 시장을 이기고 있다는 의미입니다. 섹터를 클릭하면 포함된 종목을 볼 수 있습니다." />
          <div className="ml-auto flex items-center gap-2">
            <span className="text-[11px]" style={{ color: "var(--text-faint)" }}>기간 선택</span>
            <div className="flex rounded-lg overflow-hidden" style={{ border: "1px solid var(--border)" }}>
              {PERIOD_TABS.map(p => (
                <button key={p} onClick={() => setPeriod(p)}
                  className="px-2.5 py-1 text-[12px] font-semibold transition-colors"
                  style={{
                    background: period === p ? "#ffb02018" : "transparent",
                    color: period === p ? "#ffb020" : "var(--text-muted)",
                  }}>
                  {p === "1d" ? "1일" : p === "1w" ? "1주" : p === "1m" ? "1달" : "3달"}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* 컬럼 헤더 + 행 (모바일에서는 가로 스크롤) */}
        <div className="overflow-x-auto">
        {/* 좁은 화면에선 이름·현재가 열을 숨겨 가로 스크롤 없이 상대강도까지 보이게(2026-10-21) */}
        <div className={isKR ? "sm:min-w-[480px]" : "sm:min-w-[640px]"}>
        <div className="flex items-center gap-3 px-3 py-1" style={{ borderBottom: "1px solid var(--border-dim)", background: "var(--bg-inset)" }}>
          <span className="w-20 sm:w-32 shrink-0 text-[11px] font-semibold" style={{ color: "var(--text-faint)" }}>섹터</span>
          {!isKR && <span className="hidden sm:block w-28 text-[11px]" style={{ color: "var(--text-faint)" }}>이름</span>}
          {!isKR && <span className="hidden sm:block w-16 text-[11px]" style={{ color: "var(--text-faint)" }}>현재가</span>}
          <span className="w-16 text-[11px]" style={{ color: "var(--text-faint)" }}>수익률</span>
          <span className="flex-1 text-[11px] truncate" style={{ color: "var(--text-faint)" }}>시장 대비 상대강도 (RS)<span className="hidden sm:inline"> — 중앙 기준, 우측=아웃퍼폼</span></span>
        </div>

        <div className="divide-y" style={{ borderColor: "var(--border-dim)" }}>
          {(() => {
            const maxAbsRS = Math.max(...rows.map((r: any) => Math.abs(r[`rs_${period}`] ?? 0)), 1);
            return rows.map((row: any) => {
            const key    = rowKey(row);
            const ret    = row[`ret_${period}`];
            const rs     = row[`rs_${period}`];
            const stocks = sectorStocks[key] ?? [];
            const isOpen = openKey === key;
            const barPct = rs != null ? Math.min((Math.abs(rs) / maxAbsRS) * 50, 50) : 0;

            return (
              <div key={key}>
                <button
                  onClick={() => stocks.length > 0 && setOpenKey(isOpen ? null : key)}
                  className="w-full flex items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-white/5"
                  style={{ cursor: stocks.length > 0 ? "pointer" : "default" }}
                >
                  <span className="w-20 sm:w-32 shrink-0 font-bold text-white text-[12px] truncate">{rowLabel(row)}</span>
                  {rowSubLabel(row) && (
                    <span className="hidden sm:block w-28 text-[12px] truncate" style={{ color: "var(--text-secondary)" }}>{rowSubLabel(row)}</span>
                  )}

                  {!isKR && (
                    <span className="hidden sm:block w-16 text-[12px]" style={{ color: "var(--text-muted)" }}>
                      ${row.cur_price?.toFixed(2) ?? "—"}
                    </span>
                  )}

                  <span className="w-16 text-[12px] font-bold" style={{ color: ret == null ? "var(--text-muted)" : ret >= 0 ? "#4ade80" : "#f87171" }}>
                    {pct(ret)}
                  </span>

                  <div className="flex-1 flex items-center gap-2">
                    <div className="flex-1 h-1.5 rounded-full relative" style={{ background: "var(--bg-inset)" }}>
                      {rs != null && (
                        <div className="absolute top-0 h-1.5 rounded-full"
                          style={{
                            width: `${barPct}%`,
                            left: rs >= 0 ? "50%" : `${50 - barPct}%`,
                            background: rs >= 0 ? "#4ade80" : "#f87171",
                          }} />
                      )}
                    </div>
                    <span className="w-16 text-right text-[12px] font-semibold whitespace-nowrap"
                      style={{ color: rs == null ? "var(--text-muted)" : rs >= 0 ? "#4ade80" : "#f87171" }}>
                      {pct(rs)}
                    </span>
                  </div>

                  <span className="text-[11px] w-10 sm:w-14 shrink-0 text-right" style={{ color: "var(--text-muted)" }}>
                    {stocks.length > 0 ? `${stocks.length}종목 ${isOpen ? "▲" : "▼"}` : ""}
                  </span>
                </button>

                {isOpen && stocks.length > 0 && (
                  <div className="px-3 pb-2" style={{ borderTop: "1px solid var(--border-dim)" }}>
                    <div className="flex flex-wrap gap-1.5 pt-2">
                      {stocks.map((s: any) => (
                        <div key={s.symbol} className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-[12px]"
                          style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                          <StockLink market={isKR ? "KR" : "US"} symbol={s.symbol} className="font-bold text-white">{s.symbol}</StockLink>
                          {isKR && s.name && <span style={{ color: "#a39c88" }}>{s.name}</span>}
                          {s.piotroski != null ? (
                            <span
                              className="px-1.5 rounded text-[11px] font-bold"
                              style={{
                                background: (s.piotroski >= 7 ? "#4ade80" : s.piotroski >= 5 ? "#facc15" : "#f87171") + "20",
                                color: s.piotroski >= 7 ? "#4ade80" : s.piotroski >= 5 ? "#facc15" : "#f87171",
                              }}
                            >
                              F{s.piotroski}
                            </span>
                          ) : (
                            <span style={{ color: "var(--text-faint)" }}>재무 데이터 없음</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          });
          })()}
        </div>
        </div>
        </div>
      </div>

      {benchmarkRet && (
        <div className="rounded-xl px-3 py-2 text-[12px] flex items-center gap-2 flex-wrap" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
          <span className="font-bold" style={{ color: "var(--text-muted)" }}>
            {isKR ? "KOSPI" : "SPY"} 벤치마크 수익률
          </span>
          {Object.entries(benchmarkRet).map(([label, val]: any) => (
            <span key={label} className="font-semibold" style={{ color: val >= 0 ? "#4ade80" : "#f87171" }}>
              {label}: {pct(val)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
