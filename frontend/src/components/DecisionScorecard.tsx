"use client";

import { useEffect, useState } from "react";
import { Section } from "@/src/components/Section";
import StockLink from "@/src/components/StockLink";
import { krStockName } from "@/src/lib/krStockNames";
import { CHECK_KO, CHECK_VAL_KO, DECISION_COLOR, DECISION_KO, HORIZON_KO, OutcomeLine, SOURCE_KO, pct, type Decision } from "@/src/components/DecisionPanel";

// 내 검토 기록 성적(2026-11-15, 사용자: 3개월 가상 매수 검증) - 결정별·출처별로 4·12·26주 뒤 원화 수익률과 TIGER 반도체TOP10 대비.
// 분포(건수·중앙값)와 'TIGER보다 나았던 건수'만 - 점수·순위 없음(원칙 1). 기간이 안 지난 기록은 세지 않는다.

const median = (xs: number[]) => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b), m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const num = (v: unknown) => (v == null || v === "" ? null : Number(v));

type Stat = { n: number; med: number | null; medEx: number | null; beat: number };
function stat(rows: Decision[], h: number): Stat {
  const pairs = rows.map((r) => [num(r.outcome?.[`ret_krw_${h}d`]), num(r.outcome?.[`semi_${h}d`])] as const)
    .filter(([a]) => a != null) as (readonly [number, number | null])[];
  const ex = pairs.filter(([, b]) => b != null).map(([a, b]) => a - (b as number));
  return { n: pairs.length, med: median(pairs.map(([a]) => a)), medEx: median(ex), beat: ex.filter((x) => x > 0).length };
}

function StatCell({ s }: { s: Stat }) {
  if (!s.n) return <td className="py-1.5 pr-3 text-[12px]" style={{ color: "var(--text-faint)" }}>기간 전</td>;
  return (
    <td className="py-1.5 pr-3" style={{ fontVariantNumeric: "tabular-nums" }}>
      <b style={{ color: "var(--text-primary)" }}>{pct(s.med)}</b>
      <span className="text-[12px]" style={{ color: "var(--text-muted)" }}> · TIGER 대비 {pct(s.medEx)} · {s.n}건 중 {s.beat}건 앞섬</span>
    </td>
  );
}

function Table({ title, groups }: { title: string; groups: { key: string; label: string; color?: string; rows: Decision[] }[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr style={{ color: "var(--text-muted)" }}>
            <th className="py-1 pr-3 text-left font-normal">{title}</th>
            <th className="py-1 pr-3 text-left font-normal">기록</th>
            {HORIZON_KO.map(([h, lb]) => <th key={h} className="py-1 pr-3 text-left font-normal whitespace-nowrap">{lb} 뒤 (중앙값)</th>)}
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => (
            <tr key={g.key} style={{ borderTop: "1px solid var(--border)" }}>
              <td className="py-1.5 pr-3 font-semibold whitespace-nowrap" style={{ color: g.color ?? "var(--text-primary)" }}>{g.label}</td>
              <td className="py-1.5 pr-3" style={{ color: "var(--text-secondary)" }}>{g.rows.length}</td>
              {HORIZON_KO.map(([h]) => <StatCell key={h} s={stat(g.rows, h)} />)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DecisionScorecard() {
  const [rows, setRows] = useState<Decision[] | null>(null);
  useEffect(() => {
    fetch("/api/decisions").then((r) => r.json()).then((d) => setRows(Array.isArray(d.decisions) ? d.decisions : [])).catch(() => setRows([]));
  }, []);
  if (rows == null) return null;
  const by = (k: "decision" | "source", v: string) => rows.filter((r) => r[k] === v);
  const nameOf = (r: Decision) => r.market === "KR" ? (r.name && r.name !== r.symbol ? r.name : krStockName(r.symbol)) : r.symbol;
  return (
    <Section id="mine" title="내 검토 기록 성적" sub="기업 카드에서 누른 관심·보류·제외 · 원화 기준 · TIGER 반도체TOP10 대비">
      {rows.length === 0 ? (
        <p className="text-[13px]" style={{ color: "var(--text-muted)" }}>
          아직 검토 기록이 없습니다. 기업 카드 아래 &apos;검토 기록&apos;에서 관심·보류·제외를 누르면 여기 쌓이고, 4주 뒤부터 결과가 나옵니다.
        </p>
      ) : (
        <div className="space-y-4">
          <Table title="결정" groups={(["watch", "hold", "pass"] as const).map((k) => ({ key: k, label: DECISION_KO[k], color: DECISION_COLOR[k], rows: by("decision", k) }))} />
          <Table title="'관심'의 출처" groups={(["tool", "blog", "other"] as const).map((k) => ({ key: k, label: SOURCE_KO[k], rows: by("source", k).filter((r) => r.decision === "watch") }))} />
          <div>
            <p className="h-sub mb-1">최근 기록</p>
            {rows.slice(0, 30).map((r) => (
              <div key={r.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-1.5 text-[12.5px]" style={{ borderTop: "1px solid var(--border)" }}>
                <span style={{ color: "var(--text-faint)" }}>{Number(r.decided_on.slice(5, 7))}/{Number(r.decided_on.slice(8, 10))}</span>
                <StockLink market={r.market} symbol={r.symbol} className="font-semibold" style={{ color: "var(--text-primary)" }}>{nameOf(r)}</StockLink>
                <b style={{ color: DECISION_COLOR[r.decision] }}>{DECISION_KO[r.decision]}</b>
                <span style={{ color: "var(--text-muted)" }}>
                  {Object.entries(r.checks).map(([k, v]) => `${CHECK_KO[k]} ${CHECK_VAL_KO[v]}`).join(" · ") || "확인 표시 없음"} · {SOURCE_KO[r.source]}
                </span>
                <span className="basis-full sm:basis-auto sm:ml-auto"><OutcomeLine o={r.outcome} /></span>
              </div>
            ))}
          </div>
          <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>
            시작가는 기록한 다음 거래일 종가. 미국 종목은 달러 수익률에 원/달러 변화를 곱한 원화 기준. 같은 종목을 다시 기록하면 따로 셉니다.
            건수가 적을 때(10건 미만)의 중앙값은 우연이 크게 섞입니다.
          </p>
        </div>
      )}
    </Section>
  );
}
