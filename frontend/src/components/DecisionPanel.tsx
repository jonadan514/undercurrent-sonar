"use client";

import { useEffect, useState } from "react";

// 검토 기록 칸(2026-11-15, 사용자: 3개월 가상 매수 검증) - 기업 카드에서 관심·보류·제외를 누르고, 밸류·실적·차트를 내가 어떻게 봤는지 표시.
// 글은 선택. '관심'은 다음 거래일 종가에 가상으로 샀다고 치고 4·12·26주 결과를 시장 벤치마크(미국 SPY, 한국 코스피200)와 비교한다(scripts/compute_decision_outcomes.py).
// 기록은 덮어쓰지 않는다 - 생각이 바뀌면 새로 누른다(원칙 5).

export const DECISION_KO: Record<string, string> = { watch: "관심", hold: "보류", pass: "제외" };
export const DECISION_COLOR: Record<string, string> = { watch: "var(--accent)", hold: "var(--text-secondary)", pass: "var(--text-muted)" };
export const CHECK_KO: Record<string, string> = { value: "밸류", earn: "실적", chart: "차트" };
export const CHECK_VAL_KO: Record<string, string> = { good: "좋음", mid: "보통", bad: "나쁨" };
export const SOURCE_KO: Record<string, string> = { tool: "툴 후보", blog: "블로그·뉴스", other: "기타" };
export const HORIZON_KO: [number, string][] = [[28, "4주"], [84, "12주"], [182, "26주"]];

export type Outcome = Record<string, string | number | null>;
export type Decision = {
  id: number; created_at: string; decided_on: string; market: "US" | "KR"; symbol: string; name: string | null;
  decision: string; checks: Record<string, string>; source: string; memo: string | null;
  snapshot: Record<string, unknown> | null; outcome: Outcome | null;
};

export const pct = (v: unknown) => (v == null || v === "" ? "–" : `${Number(v) >= 0 ? "+" : ""}${(Number(v) * 100).toFixed(1)}%`);
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;

/** 결과 한 줄 - 수익률과 같은 기간 시장 벤치마크(종목과 같은 통화). 아직 기간이 안 지났으면 '–' */
export function OutcomeLine({ o }: { o: Outcome | null }) {
  if (!o || o.entry_price == null) return <span style={{ color: "var(--text-faint)" }}>시작가 대기(다음 거래일 종가)</span>;
  return (
    <span style={{ fontVariantNumeric: "tabular-nums" }}>
      <span style={{ color: "var(--text-faint)" }}>{md(String(o.entry_date))} 시작 · </span>
      {HORIZON_KO.map(([h, lb], i) => {
        const r = o[`ret_${h}d`], s = o[`mkt_${h}d`];
        return (
          <span key={h}>{i > 0 && <span style={{ color: "var(--text-faint)" }}> · </span>}
            {lb} <b style={{ color: r == null ? "var(--text-faint)" : "var(--text-primary)" }}>{pct(r)}</b>
            {r != null && s != null && <span style={{ color: "var(--text-muted)" }}> (시장 {pct(s)})</span>}
          </span>
        );
      })}
    </span>
  );
}

function Seg<T extends string>({ value, options, onChange, labels }: { value: T | null; options: T[]; onChange: (v: T | null) => void; labels: Record<string, string> }) {
  return (
    <span className="inline-flex flex-wrap gap-1">
      {options.map((o) => {
        const on = value === o;
        return (
          <button key={o} type="button" onClick={() => onChange(on ? null : o)}
            className="rounded px-2.5 py-1 text-[12.5px]"
            style={{ border: `1px solid ${on ? "var(--accent)" : "var(--border)"}`, color: on ? "var(--accent)" : "var(--text-secondary)",
                     background: on ? "rgba(255,176,32,0.1)" : "transparent" }}>
            {labels[o]}
          </button>
        );
      })}
    </span>
  );
}

export default function DecisionPanel({ market, symbol, name, fromTool }: { market: "US" | "KR"; symbol: string; name?: string | null; fromTool: boolean }) {
  const [rows, setRows] = useState<Decision[] | null>(null);
  const [today, setToday] = useState("");
  const [decision, setDecision] = useState<string | null>(null);
  const [checks, setChecks] = useState<Record<string, string | null>>({ value: null, earn: null, chart: null });
  const [source, setSource] = useState<string | null>(fromTool ? "tool" : null);
  const [memo, setMemo] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = () => fetch(`/api/decisions?market=${market}&symbol=${encodeURIComponent(symbol)}`).then((r) => r.json())
    .then((d) => { setRows(Array.isArray(d.decisions) ? d.decisions : []); setToday(d.today ?? ""); }).catch(() => setRows([]));
  useEffect(() => { load(); }, [market, symbol]);   // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    if (!decision || !source) { setMsg("결정과 어디서 봤는지는 골라 주세요"); return; }
    setBusy(true); setMsg("");
    try {
      const r = await fetch("/api/decisions", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ market, symbol, name, decision, checks, source, memo }) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "저장 실패");
      setDecision(null); setChecks({ value: null, earn: null, chart: null }); setMemo("");
      setMsg("저장했습니다"); load();
    } catch (e) { setMsg(e instanceof Error ? e.message : "저장 실패"); }
    setBusy(false);
  };
  const del = async (id: number) => {
    const r = await fetch(`/api/decisions?id=${id}`, { method: "DELETE" });
    if (r.ok) load(); else setMsg((await r.json()).error ?? "지우기 실패");
  };

  const label = "w-[5.5rem] shrink-0 text-[12.5px]";
  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className={label} style={{ color: "var(--text-muted)" }}>결정</span>
        <Seg value={decision} options={["watch", "hold", "pass"]} onChange={setDecision} labels={{ watch: "관심 (가상 매수)", hold: "보류", pass: "제외" }} />
      </div>
      {(["value", "earn", "chart"] as const).map((k) => (
        <div key={k} className="flex flex-wrap items-center gap-2">
          <span className={label} style={{ color: "var(--text-muted)" }}>내가 본 {CHECK_KO[k]}</span>
          <Seg value={checks[k]} options={["good", "mid", "bad"]} onChange={(v) => setChecks((c) => ({ ...c, [k]: v }))} labels={CHECK_VAL_KO} />
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2">
        <span className={label} style={{ color: "var(--text-muted)" }}>어디서 봤나</span>
        <Seg value={source} options={["tool", "blog", "other"]} onChange={setSource} labels={SOURCE_KO} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className={label} style={{ color: "var(--text-muted)" }}>한 줄(선택)</span>
        <input value={memo} onChange={(e) => setMemo(e.target.value)} maxLength={200} placeholder="예: HBM 수주 기대, 차트는 200일선 회복 대기"
          className="min-w-0 flex-1 rounded px-2 py-1 text-[13px]" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)", color: "var(--text-primary)" }} />
        <button type="button" onClick={save} disabled={busy} className="rounded px-3 py-1 text-[13px] font-semibold"
          style={{ background: "rgba(255,176,32,0.15)", border: "1px solid var(--accent)", color: "var(--accent)", opacity: busy ? 0.5 : 1 }}>
          기록
        </button>
      </div>
      {msg && <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>{msg}</p>}
      <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>
        &apos;관심&apos;은 다음 거래일 종가에 가상으로 샀다고 치고 4·12·26주 뒤 결과를 시장 벤치마크(미국 SPY, 한국 코스피200)와 비교합니다(보류·제외도 같은 방식으로 재서
        &apos;제외한 게 맞았는지&apos;도 봅니다). 그때의 밸류·실적·차트 값은 자동으로 함께 저장됩니다. 생각이 바뀌면 새로 누르세요 - 예전 기록은 남습니다.
      </p>
      {rows && rows.length > 0 && (
        <div className="pt-1" style={{ borderTop: "1px solid var(--border)" }}>
          {rows.map((r) => (
            <div key={r.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-1.5 text-[12.5px]" style={{ borderBottom: "1px solid var(--border-dim, var(--border))" }}>
              <span style={{ color: "var(--text-faint)" }}>{md(r.decided_on)}</span>
              <b style={{ color: DECISION_COLOR[r.decision] }}>{DECISION_KO[r.decision]}</b>
              <span style={{ color: "var(--text-muted)" }}>
                {Object.entries(r.checks).map(([k, v]) => `${CHECK_KO[k]} ${CHECK_VAL_KO[v]}`).join(" · ") || "확인 표시 없음"} · {SOURCE_KO[r.source]}
              </span>
              {r.memo && <span style={{ color: "var(--text-secondary)" }}>“{r.memo}”</span>}
              <span className="basis-full sm:basis-auto sm:ml-auto"><OutcomeLine o={r.outcome} /></span>
              {r.decided_on === today && (
                <button type="button" onClick={() => del(r.id)} className="text-[11.5px] hover:underline" style={{ color: "var(--text-faint)" }}>지우기</button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
