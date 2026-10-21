"use client";

// 관찰 노트 공용 UI (2026-10-05) - 작성 창과 "그때 vs 지금" 카드. 규칙은 app/api/notes/route.ts 참고:
// 가설·그때 값은 고치지 않고, 회고의 판단·배운 점만 사람이 붙인다. 툴은 기대가 일어났는지 사실만 적는다.

import { useState } from "react";
import StockLink from "@/src/components/StockLink";
import Link from "next/link";
import { X } from "lucide-react";
import { themeName } from "@/src/lib/themeNames";
import { krStockName } from "@/src/lib/krStockNames";

const GOOD = "var(--good)";
const DANGER = "var(--danger)";
const MUTED = "var(--text-muted)";
const FAINT = "var(--text-faint)";
const ACCENT = "var(--accent)";
const MONO = 'ui-monospace, "SF Mono", "Cascadia Code", "Roboto Mono", monospace';

export type Kind = "theme" | "stock";
type Snap = Record<string, unknown> | null;

export interface Review {
  checkpoint: number;
  reviewed_at: string;
  week_start: string;
  snapshot: Snap;
  expect_results: Record<string, boolean | null> | null;
  verdict: string | null;
  lesson: string | null;
}

export interface ObservationT {
  id: number;
  created_at: string;
  kind: Kind;
  market: "US" | "KR";
  theme_id: string | null;
  ticker: string | null;
  hypothesis: string;
  expects: string[];
  week_start: string;
  snapshot: Snap;
  reviews: Review[];
}

// 축마다 ↑ 또는 ↓ 하나(2026-10-05 - 하향 가설도 남길 수 있게). earn_hold는 첫 버전 키라 읽기만 한다.
export const EXPECT_LABEL: Record<Kind, Record<string, string>> = {
  theme: { news_up: "뉴스 ↑", news_down: "뉴스 ↓", earn_up: "실적 ↑", earn_down: "실적 ↓",
           price_up: "주가 ↑", price_down: "주가 ↓", earn_hold: "실적 ↑ 유지", unsure: "잘 모르겠음" },
  stock: { news_up: "소속 테마 뉴스 ↑", news_down: "소속 테마 뉴스 ↓", earn_up: "실적 중앙값 초과", earn_down: "실적 중앙값 미달",
           price_up: "지수보다 더 오름", price_down: "지수보다 덜 오름", earn_hold: "실적 중앙값 초과 유지", unsure: "잘 모르겠음" },
};
const AXES_FORM: { axis: "news" | "earn" | "price"; label: Record<Kind, string>; hint: Record<Kind, string> }[] = [
  { axis: "price", label: { theme: "주가", stock: "주가" }, hint: { theme: "소속 중앙값의 지수 대비 4주 흐름", stock: "작성일부터 지수와 비교" } },
  { axis: "earn", label: { theme: "실적", stock: "실적" }, hint: { theme: "매출 성장률이 시장 중앙값을 넘는 기업 비율", stock: "매출 성장률 시장 중앙값 초과/미달" } },
  { axis: "news", label: { theme: "뉴스", stock: "테마 뉴스" }, hint: { theme: "기사 수가 8주 기준선보다 많아짐/줄어듦", stock: "소속 테마 중 하나라도" } },
];
const VERDICT_LABEL: Record<string, string> = { right: "맞았다", wrong: "틀렸다", unclear: "애매" };

type Arrow = string | null | undefined;
const isUp = (a: Arrow) => a === "up1" || a === "up2";
const glyph = (a: Arrow) => (a === "up2" ? "↑↑" : a === "up1" ? "↑" : a === "flat" ? "→" : a === "down" ? "↓" : "–");
const arrowColor = (a: Arrow) => (isUp(a) ? GOOD : a === "down" ? DANGER : a === "flat" ? MUTED : FAINT);
const pct = (n: unknown) => (typeof n === "number" ? `${n >= 0 ? "+" : ""}${(n * 100).toFixed(1)}%` : "-");
const md = (d: string) => { const [, m, day] = d.slice(0, 10).split("-"); return `${Number(m)}/${Number(day)}`; };

export function targetName(o: { kind: Kind; market: string; theme_id: string | null; ticker: string | null }): string {
  if (o.kind === "theme") return themeName(o.theme_id ?? "").ko;
  const t = o.ticker ?? "";
  return o.market === "KR" ? `${krStockName(t) || t}` : t;
}

/** 상태: 판단할 회고가 있음 / 진행 중 / 12주 판단까지 끝남 */
export function obsStatus(o: ObservationT): "due" | "open" | "done" {
  if (o.reviews.some((r) => !r.verdict)) return "due";
  if (o.reviews.some((r) => r.checkpoint === 12 && r.verdict)) return "done";
  return "open";
}

// ── 작성 창 ──────────────────────────────────────────────────────────────────

export function ObservationForm({ kind, market, themeId, ticker, title, onClose, onSaved }: {
  kind: Kind; market: "US" | "KR"; themeId?: string; ticker?: string; title: string;
  onClose: () => void; onSaved?: () => void;
}) {
  const [hypothesis, setHypothesis] = useState("");
  const [expects, setExpects] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 한 축에서는 ↑/↓ 중 하나만(다시 누르면 해제). "잘 모르겠음" 칩은 없앴다 - 모르는 축은 고르지 않으면 되고,
  // 다른 칩을 다 지우는 동작이 리셋처럼 보였다(2026-10-05 사용자 의견). 아무것도 안 고르면 저장할 때 unsure.
  const toggle = (e: string) => setExpects((cur) => {
    if (cur.includes(e)) return cur.filter((x) => x !== e);
    const axis = e.split("_")[0];
    return [...cur.filter((x) => x !== "unsure" && !x.startsWith(`${axis}_`)), e];
  });

  const save = async () => {
    setSaving(true); setError(null);
    try {
      const res = await fetch("/api/notes", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, market, theme_id: themeId, ticker, hypothesis, expects: expects.length ? expects : ["unsure"] }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) { setError(d.error ?? "저장하지 못했습니다"); return; }
      onSaved?.(); onClose();
    } catch { setError("저장하지 못했습니다"); } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.6)" }} onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl p-5" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
        onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-start gap-2">
          <div className="flex-1">
            <p className="text-[12px]" style={{ color: MUTED }}>관찰 남기기 · {market === "US" ? "미국" : "한국"}</p>
            <h3 className="text-[17px] font-bold" style={{ color: "var(--text-primary)" }}>{title}</h3>
          </div>
          <button onClick={onClose} aria-label="닫기" style={{ color: MUTED }}><X size={18} /></button>
        </div>

        <label className="mb-1 block text-[12px]" style={{ color: MUTED }}>가설 (한 줄, 필수)</label>
        <textarea value={hypothesis} onChange={(e) => setHypothesis(e.target.value)} maxLength={300} rows={2}
          placeholder={kind === "theme" ? "예: 실적이 8주째 앞서는데 주가는 막 따라붙는 중. 뉴스는 아직" : "예: 테마 흐름 안에서 싸고 성장 중. 실적이 이어지면 재평가"}
          className="w-full resize-none rounded-lg p-2.5 text-[14px] outline-none"
          style={{ background: "var(--bg-inset)", border: "1px solid var(--border-ctrl)", color: "var(--text-primary)" }} />

        <p className="mb-1.5 mt-3 text-[12px]" style={{ color: MUTED }}>4주·12주 뒤 어떻게 될 것 같나요? (선택 - 축마다 ↑ 또는 ↓, 여러 축 가능)</p>
        <div className="space-y-1.5">
          {AXES_FORM.map(({ axis, label, hint }) => (
            <div key={axis} className="flex flex-wrap items-center gap-1.5">
              <span className="w-16 shrink-0 text-[12px]" style={{ color: "var(--text-secondary)" }} title={hint[kind]}>{label[kind]}</span>
              {(["up", "down"] as const).map((dir) => {
                const k = `${axis}_${dir}`, on = expects.includes(k);
                return (
                  <button key={k} onClick={() => toggle(k)} className="whitespace-nowrap rounded-lg px-3 py-1.5 text-[12px]"
                    style={{ background: on ? "rgba(255,176,32,0.14)" : "transparent", color: on ? ACCENT : MUTED,
                             border: `1px solid ${on ? "rgba(255,176,32,0.45)" : "var(--border-ctrl)"}` }}>
                    {EXPECT_LABEL[kind][k]}
                  </button>
                );
              })}
              <span className="text-[11px]" style={{ color: FAINT }}>{hint[kind]}</span>
            </div>
          ))}
          <p className="pt-0.5 text-[11px]" style={{ color: FAINT }}>
            고르지 않은 축은 회고에서 &quot;일어났나&quot;를 따지지 않습니다. 아무것도 고르지 않으면 &quot;잘 모르겠음&quot;으로 저장됩니다.
          </p>
        </div>

        <p className="mt-3 text-[12px] leading-relaxed" style={{ color: FAINT }}>
          4주 뒤와 12주 뒤에 "그때 vs 지금"이 자동으로 붙습니다. 저장할 때 지금의 {kind === "theme" ? "세 축·라벨·지수 대비 주가" : "소속 테마 세 축·실적 판정·재무 꼬리표"}가 함께 저장되고,
          가설은 나중에 고칠 수 없습니다(회고 전까지는 지울 수 있음).
        </p>
        {error && <p className="mt-2 text-[12px]" style={{ color: DANGER }}>{error}</p>}
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-[13px]" style={{ color: MUTED, border: "1px solid var(--border-ctrl)" }}>취소</button>
          <button onClick={save} disabled={!hypothesis.trim() || saving} className="rounded-lg px-4 py-2 text-[13px] font-bold"
            style={{ background: hypothesis.trim() ? ACCENT : "var(--border-ctrl)", color: "#000", opacity: saving ? 0.6 : 1 }}>
            {saving ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── 그때 vs 지금 카드 ─────────────────────────────────────────────────────────

function ThemeRows({ cols }: { cols: { head: string; snap: Snap }[] }) {
  const rows: { label: string; render: (s: Snap) => React.ReactNode }[] = [
    { label: "뉴스", render: (s) => <b style={{ color: arrowColor(s?.news_arrow as Arrow) }}>{glyph(s?.news_arrow as Arrow)}</b> },
    { label: "실적", render: (s) => <b style={{ color: arrowColor(s?.earn_arrow as Arrow) }}>{glyph(s?.earn_arrow as Arrow)}</b> },
    { label: "주가", render: (s) => <b style={{ color: arrowColor(s?.price_arrow as Arrow) }}>{glyph(s?.price_arrow as Arrow)}</b> },
    { label: "라벨", render: (s) => <span style={{ color: s?.label ? ACCENT : FAINT }}>{(s?.label as string) ?? "없음"}</span> },
    { label: "지수 대비", render: (s) => <span>{typeof s?.price_excess === "number" ? `${pct(s.price_excess)}p` : "-"}</span> },
  ];
  return <SnapTable cols={cols} rows={rows} />;
}

function StockRows({ cols }: { cols: { head: string; snap: Snap }[] }) {
  const themeUps = (s: Snap) => {
    const ts = (s?.themes as Record<string, Arrow>[] | undefined) ?? [];
    if (!ts.length) return "-";
    const n = (k: string) => ts.filter((t) => isUp(t[k])).length;
    return `${ts.length}개 · 뉴스↑${n("news_arrow")} 실적↑${n("earn_arrow")} 주가↑${n("price_arrow")}`;
  };
  const rows: { label: string; render: (s: Snap) => React.ReactNode }[] = [
    { label: "작성 이후", render: (s) => (s && "ret_since" in s
      ? <span><b style={{ color: typeof s.ret_since === "number" && s.ret_since >= 0 ? GOOD : DANGER }}>{pct(s.ret_since)}</b>
          <span style={{ color: FAINT }}> (지수 {pct(s.index_ret_since)})</span></span>
      : <span style={{ color: FAINT }}>기준</span>) },
    { label: "4주 수익률", render: (s) => pct(s?.price_ret_4w) },
    { label: "실적", render: (s) => ({ improved: "중앙값 초과", not_improved: "미달", insufficient: "데이터부족" } as Record<string, string>)[s?.earn_status as string] ?? "-" },
    { label: "밸류·성장", render: (s) => [s?.valuation_tier, s?.growth_tier].filter(Boolean).join(" · ") || "-" },
    { label: "소속 테마", render: (s) => <span className="text-[11px]">{themeUps(s)}</span> },
  ];
  return <SnapTable cols={cols} rows={rows} />;
}

function SnapTable({ cols, rows }: { cols: { head: string; snap: Snap }[]; rows: { label: string; render: (s: Snap) => React.ReactNode }[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[13px]" style={{ minWidth: 360 }}>
        <thead>
          <tr style={{ color: FAINT }}>
            <th className="w-20 py-1 text-left font-normal" />
            {cols.map((c) => <th key={c.head} className="py-1 text-left font-normal whitespace-nowrap">{c.head}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} style={{ borderTop: "1px solid var(--border-dim)" }}>
              <td className="py-1.5 text-[12px]" style={{ color: MUTED }}>{r.label}</td>
              {cols.map((c) => <td key={c.head} className="py-1.5" style={{ fontFamily: MONO, color: "var(--text-secondary)" }}>{r.render(c.snap)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReviewJudge({ o, r, onChanged }: { o: ObservationT; r: Review; onChanged: () => void }) {
  const [verdict, setVerdict] = useState<string | null>(r.verdict);
  const [lesson, setLesson] = useState(r.lesson ?? "");
  const [saving, setSaving] = useState(false);
  const save = async (v: string | null, l: string) => {
    setSaving(true);
    try {
      await fetch("/api/notes", { method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ observation_id: o.id, checkpoint: r.checkpoint, verdict: v, lesson: l }) });
      onChanged();
    } finally { setSaving(false); }
  };
  const results = Object.entries(r.expect_results ?? {});
  return (
    <div className="mt-2 rounded-lg p-3" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
      <p className="text-[12px]" style={{ color: MUTED }}>
        {r.checkpoint}주 회고 · {md(r.reviewed_at)}
        {results.length > 0 && <> · 기대한 것: {results.map(([k, v], i) => (
          <span key={k}>{i > 0 && ", "}{EXPECT_LABEL[o.kind][k] ?? k} → <b style={{ color: v == null ? FAINT : v ? GOOD : DANGER }}>
            {v == null ? "판단 불가(데이터 부족)" : v ? "일어남" : "일어나지 않음"}</b></span>))}</>}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-[12px]" style={{ color: MUTED }}>내 판단</span>
        {Object.entries(VERDICT_LABEL).map(([k, label]) => (
          <button key={k} disabled={saving} onClick={() => { const v = verdict === k ? null : k; setVerdict(v); save(v, lesson); }}
            className="rounded-lg px-3 py-1 text-[12px]"
            style={{ background: verdict === k ? "rgba(255,176,32,0.14)" : "transparent", color: verdict === k ? ACCENT : MUTED,
                     border: `1px solid ${verdict === k ? "rgba(255,176,32,0.45)" : "var(--border-ctrl)"}` }}>{label}</button>
        ))}
      </div>
      <div className="mt-2 flex gap-1.5">
        <input value={lesson} onChange={(e) => setLesson(e.target.value)} maxLength={300} placeholder="배운 점 한 줄 (선택)"
          className="min-w-0 flex-1 rounded-lg px-2.5 py-1.5 text-[13px] outline-none"
          style={{ background: "var(--bg-card)", border: "1px solid var(--border-ctrl)", color: "var(--text-primary)" }} />
        <button disabled={saving || lesson === (r.lesson ?? "")} onClick={() => save(verdict, lesson)}
          className="rounded-lg px-3 text-[12px]" style={{ color: lesson === (r.lesson ?? "") ? FAINT : ACCENT, border: "1px solid var(--border-ctrl)" }}>저장</button>
      </div>
    </div>
  );
}

export function ObservationCard({ o, currentWeek, onChanged, showTarget = true }: {
  o: ObservationT; currentWeek?: string; onChanged: () => void; showTarget?: boolean;
}) {
  const status = obsStatus(o);
  const cols = [{ head: `그때 ${md(o.created_at)}`, snap: o.snapshot },
                ...o.reviews.map((r) => ({ head: `${r.checkpoint}주 뒤 ${md(r.reviewed_at)}`, snap: r.snapshot }))];
  const next = [4, 12].find((n) => !o.reviews.some((r) => r.checkpoint === n));
  let wait: string | null = null;
  if (next && currentWeek) {
    const due = new Date(`${o.week_start}T00:00:00Z`);
    due.setUTCDate(due.getUTCDate() + 7 * next);
    const weeksLeft = Math.max(0, Math.ceil((due.getTime() - new Date(`${currentWeek}T00:00:00Z`).getTime()) / (7 * 864e5)));
    wait = weeksLeft > 0 ? `${next}주 회고까지 ${weeksLeft}주` : `${next}주 회고 - 이번 주간 계산 뒤에 붙습니다`;
  }
  const remove = async () => {
    if (!confirm("이 관찰을 지울까요? (회고가 붙기 전이라 지울 수 있습니다)")) return;
    await fetch(`/api/notes?id=${o.id}`, { method: "DELETE" });
    onChanged();
  };
  return (
    <div className="rounded-xl p-4" style={{ background: "var(--bg-card)", border: `1px solid ${status === "due" ? "rgba(255,176,32,0.45)" : "var(--border)"}` }}>
      <div className="mb-1 flex flex-wrap items-center gap-2 text-[12px]" style={{ color: MUTED }}>
        <span style={{ color: status === "due" ? ACCENT : status === "done" ? FAINT : MUTED }}>
          {status === "due" ? "🔁 회고 도착" : status === "done" ? "정리됨" : "⏳ 진행 중"}
        </span>
        <span>· {md(o.created_at)} 작성</span>
        {showTarget && <span>· {o.kind === "stock" && o.ticker
          ? <StockLink market={o.market} symbol={o.ticker}><b style={{ color: "var(--text-primary)" }}>{targetName(o)}</b></StockLink>
          : <b style={{ color: "var(--text-primary)" }}>{targetName(o)}</b>} ({o.market === "US" ? "미국" : "한국"}{o.kind === "stock" ? " · 종목" : ""})</span>}
        {wait && <span>· {wait}</span>}
        <span className="ml-auto flex gap-3">
          {o.kind === "theme" && o.theme_id && (
            <Link href={`/radar/theme?id=${encodeURIComponent(o.theme_id)}&market=${o.market}`} style={{ color: ACCENT }}>테마 이력 →</Link>
          )}
          {o.reviews.length === 0 && <button onClick={remove} style={{ color: FAINT }}>지우기</button>}
        </span>
      </div>
      <p className="mb-2 text-[14px]" style={{ color: "var(--text-primary)" }}>&ldquo;{o.hypothesis}&rdquo;</p>
      {o.expects.length > 0 && (
        <p className="mb-2 text-[12px]" style={{ color: MUTED }}>기대: {o.expects.map((e) => EXPECT_LABEL[o.kind][e] ?? e).join(" · ")}</p>
      )}
      {o.kind === "theme" ? <ThemeRows cols={cols} /> : <StockRows cols={cols} />}
      {o.reviews.map((r) => <ReviewJudge key={r.checkpoint} o={o} r={r} onChanged={onChanged} />)}
    </div>
  );
}
