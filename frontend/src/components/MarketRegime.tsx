"use client";

// 시장 환경(레짐) 칸 - 2026-11-07, 마스터 플랜 2단계(사용자 결정: 축별 표시 + 정해진 조합에만 이름).
// 축마다 그 지표 자신의 지난 1년과 비교한 수준(높은 편/보통/낮은 편)과 최근 4주 방향(평소 4주 변화폭 대비)을 따로 보여 주고,
// 정해진 조합에만 이름을 붙인다(src/analyzers/regime.py COMBOS). 종합 점수·등급·행동 지시 없음(원칙 1).
// 화살표 색은 좋고 나쁨이 아니라 방향만(오름 = 밝게, 내림 = 청록, 큰 변화 없음 = 흐리게) - VIX↑와 금리↓처럼 지표마다 뜻이 달라서.

type Axis = { name: string; key: string; label: string; value: number | null; chg: number | null; level: string | null; dir: string | null; n: number };
type Week = { week: string; as_of: string; axes: Record<string, Axis>; combos: { id: string; name: string; meaning: string }[] };
export type RegimeData = Record<"US" | "KR", Week[]>;

const ARROW: Record<string, string> = { up: "↑", flat: "→", down: "↓" };
const DIR_COLOR: Record<string, string> = { up: "var(--text-primary)", flat: "var(--text-faint)", down: "#6fb3b8" };
const LEVEL_KO: Record<string, string> = { high: "높은 편", mid: "보통", low: "낮은 편" };
const MKT = { US: { flag: "🇺🇸", name: "미국" }, KR: { flag: "🇰🇷", name: "한국" } } as const;

function fmt(key: string, v: number | null, chg = false): string {
  if (v == null) return "-";
  const s = chg && v > 0 ? "+" : "";
  if (key === "kospi_foreign") return `${v > 0 ? "+" : ""}${(v / 1e12).toFixed(1)}조`;
  if (key === "usdkrw") return `${s}${Math.round(v).toLocaleString()}원`;
  if (["us10y", "kr3y", "kr10y", "real10y"].includes(key)) return `${s}${v.toFixed(2)}${chg ? "%p" : "%"}`;
  if (["hy_spread", "spread_10y_2y"].includes(key)) return `${s}${v.toFixed(2)}%p`;
  return `${s}${v.toFixed(2)}`;
}

function MarketCol({ m, weeks }: { m: "US" | "KR"; weeks: Week[] }) {
  const last = weeks[weeks.length - 1];
  if (!last) return <p className="text-[12.5px]" style={{ color: "var(--text-muted)" }}>{MKT[m].flag} {MKT[m].name} - 아직 계산 전</p>;
  const axisKeys = Object.keys(last.axes);
  return (
    <div className="rounded-lg p-3" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13.5px] font-bold" style={{ color: "var(--text-primary)" }}>{MKT[m].flag} {MKT[m].name}</span>
        {last.combos.length ? last.combos.map((c) => (
          <span key={c.id} className="rounded px-1.5 py-0.5 text-[12px] font-bold" style={{ background: "#ffb02022", color: "#ffb020" }} title={c.meaning}>{c.name}</span>
        )) : <span className="text-[12px]" style={{ color: "var(--text-faint)" }}>정해진 조합 없음</span>}
        <span className="ml-auto text-[11px]" style={{ color: "var(--text-faint)" }}>{last.as_of.slice(5).replace("-", "/")} 기준 · 최근 4주</span>
      </div>
      {last.combos.length > 0 && <p className="mt-1 text-[11.5px]" style={{ color: "var(--text-muted)" }}>{last.combos.map((c) => `${c.name}: ${c.meaning}`).join(" / ")}</p>}
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-[12px]" style={{ fontVariantNumeric: "tabular-nums" }}>
          <thead>
            <tr style={{ color: "var(--text-faint)" }}>
              <th className="py-1 text-left font-normal">축</th>
              <th className="py-1 text-right font-normal">값</th>
              <th className="py-1 text-right font-normal">4주 변화</th>
              <th className="py-1 pl-2 text-left font-normal">1년 중</th>
              {weeks.map((w, i) => (
                <th key={w.week} className="py-1 text-center font-normal text-[10px] w-5 whitespace-nowrap" title={`${w.as_of} 기준`}>
                  {i === 0 || w.as_of.slice(5, 7) !== weeks[i - 1].as_of.slice(5, 7) ? `${Number(w.as_of.slice(5, 7))}월` : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {axisKeys.map((k) => {
              const a = last.axes[k];
              return (
                <tr key={k} style={{ borderTop: "1px solid var(--border-dim, var(--border))" }}>
                  <td className="py-1 pr-2 whitespace-nowrap" title={a.label}>
                    <span style={{ color: "var(--text-secondary)" }}>{a.name}</span>
                    <span className="ml-1 text-[10.5px]" style={{ color: "var(--text-faint)" }}>{a.label}</span>
                  </td>
                  <td className="py-1 text-right whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>{fmt(a.key, a.value)}</td>
                  <td className="py-1 text-right whitespace-nowrap" style={{ color: a.dir ? DIR_COLOR[a.dir] : "var(--text-faint)" }}>
                    {a.dir ? ARROW[a.dir] : ""} {a.key === "kospi_foreign" ? "" : fmt(a.key, a.chg, true)}
                  </td>
                  <td className="py-1 pl-2 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>
                    {a.dir == null ? "데이터 부족" : a.key === "kospi_foreign" ? (a.level === "high" ? "순매수" : a.level === "low" ? "순매도" : "-") : LEVEL_KO[a.level ?? ""] ?? "-"}
                  </td>
                  {weeks.map((w) => {
                    const x = w.axes[k];
                    return <td key={w.week} className="py-1 text-center" style={{ color: x?.dir ? DIR_COLOR[x.dir] : "var(--text-faint)" }}
                      title={`${w.as_of} ${a.name} ${x?.dir ? ARROW[x.dir] : "데이터 부족"}`}>{x?.dir ? ARROW[x.dir] : "·"}</td>;
                  })}
                </tr>
              );
            })}
            <tr style={{ borderTop: "1px solid var(--border)" }}>
              <td colSpan={4} className="py-1 text-[11px]" style={{ color: "var(--text-faint)" }}>조합 (주별)</td>
              {weeks.map((w) => (
                <td key={w.week} className="py-1 text-center text-[10px] font-bold" style={{ color: "#ffb020" }} title={`${w.as_of} ${w.combos.map((c) => c.name).join(", ") || "조합 없음"}`}>
                  {w.combos.map((c) => c.name.slice(0, 1)).join("") || ""}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function MarketRegime({ data }: { data: RegimeData }) {
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">
        <MarketCol m="US" weeks={data.US ?? []} />
        <MarketCol m="KR" weeks={data.KR ?? []} />
      </div>
      <p className="text-[11.5px] leading-relaxed" style={{ color: "var(--text-faint)" }}>
        축마다 그 지표 자신의 지난 1년과 비교합니다: 1년 중 상·하위 20%면 높은/낮은 편, 최근 4주 변화가 평소 4주 변화폭보다 크면 화살표.
        정해진 조합(위험 회피·위험 선호·긴축 압력·완화 기대·원화 약세 압력)에만 이름을 붙이고, 점수나 매수·매도 판단은 없습니다.
        오른쪽 칸은 지난 12주의 주별 방향, 맨 아래 글자는 그 주의 조합 이름 첫 글자입니다. 신용·변동성은 미국 지표를 두 시장에 같이 씁니다.
      </p>
    </div>
  );
}
