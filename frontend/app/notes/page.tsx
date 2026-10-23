"use client";

// 관찰 노트 (2026-10-05) - 내가 남긴 가설과 4주·12주 회고. 판정은 사람이 하고, 툴은 그때와 지금을 나란히 놓는다.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { EXPECT_LABEL, ObservationCard, ObservationT, obsStatus } from "@/src/components/Observation";
import PageHeader from "@/src/components/PageHeader";
import EmptyState from "@/src/components/EmptyState";

const MUTED = "var(--text-muted)";
const FAINT = "var(--text-faint)";
const ACCENT = "var(--accent)";
const GOOD = "var(--good)";

type Tab = "due" | "open" | "done";
const TAB_LABEL: Record<Tab, string> = { due: "회고 도착", open: "진행 중", done: "정리됨" };

export default function NotesPage() {
  const [items, setItems] = useState<ObservationT[]>([]);
  const [currentWeek, setCurrentWeek] = useState<string | undefined>();
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("due");
  const [kind, setKind] = useState<"all" | "theme" | "stock">("all");

  const load = useCallback(() => {
    fetch("/api/notes")
      .then((r) => r.json())
      .then((d) => { setItems(Array.isArray(d.observations) ? d.observations : []); setCurrentWeek(d.current_week); })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const byKind = items.filter((o) => kind === "all" || o.kind === kind);
  const counts = { due: 0, open: 0, done: 0 } as Record<Tab, number>;
  byKind.forEach((o) => counts[obsStatus(o)]++);
  const shown = byKind.filter((o) => obsStatus(o) === tab);
  // 처음 열었을 때 회고 도착이 없으면 진행 중 탭으로
  useEffect(() => {
    if (!loading && counts.due === 0 && tab === "due" && counts.open > 0) setTab("open");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  // 쌓인 뒤 요약 - 회고 하나하나를 센다(4주·12주 각각)
  const reviews = byKind.flatMap((o) => o.reviews.map((r) => ({ o, r })));
  const verdicts = { right: 0, wrong: 0, unclear: 0 } as Record<string, number>;
  reviews.forEach(({ r }) => { if (r.verdict) verdicts[r.verdict]++; });
  const expectStats: Record<string, { n: number; yes: number; kind: string }> = {};
  reviews.forEach(({ o, r }) => Object.entries(r.expect_results ?? {}).forEach(([k, v]) => {
    if (v == null) return;
    const key = `${o.kind}:${k}`;
    expectStats[key] ??= { n: 0, yes: 0, kind: o.kind };
    expectStats[key].n++;
    if (v) expectStats[key].yes++;
  }));
  const judged = verdicts.right + verdicts.wrong + verdicts.unclear;

  const chip = (active: boolean) => ({
    background: active ? "rgba(255,176,32,0.14)" : "transparent", color: active ? ACCENT : MUTED,
    border: `1px solid ${active ? "rgba(255,176,32,0.45)" : "var(--border-ctrl)"}`,
  });

  return (
    <div className="mx-auto w-full max-w-[1280px] space-y-4 pb-10">
      <PageHeader title="관찰 노트" intro="notes"
        desc="테마·종목에 남긴 가설과, 4주·12주 뒤 그때와 지금. 판단은 직접 하고 배운 점을 한 줄씩 쌓습니다." />

      {judged + Object.keys(expectStats).length > 0 && (
        <div className="rounded-2xl p-4 text-[13px]" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
          {judged > 0 && (
            <p style={{ color: MUTED }}>내 판단 (회고 {judged}건): <b style={{ color: GOOD }}>맞았다 {verdicts.right}</b> · 틀렸다 {verdicts.wrong} · 애매 {verdicts.unclear}</p>
          )}
          {Object.keys(expectStats).length > 0 && (
            <p className="mt-1" style={{ color: MUTED }}>기대별 실제:{" "}
              {Object.entries(expectStats).map(([key, s], i) => (
                <span key={key}>{i > 0 && " · "}{s.kind === "stock" ? "종목 " : ""}{EXPECT_LABEL[s.kind as "theme" | "stock"][key.split(":")[1]]} {s.n}번 중 {s.yes}번 일어남</span>
              ))}
            </p>
          )}
          <p className="mt-1 text-[12px]" style={{ color: FAINT }}>데이터 부족으로 판단할 수 없던 회고는 세지 않습니다.</p>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {(["due", "open", "done"] as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)} className="rounded-lg px-3 py-1.5 text-[13px]" style={chip(tab === t)}>
            {TAB_LABEL[t]} {counts[t]}
          </button>
        ))}
        <span className="mx-1 h-5 w-px" style={{ background: "var(--border-ctrl)" }} />
        {(["all", "theme", "stock"] as const).map((k) => (
          <button key={k} onClick={() => setKind(k)} className="rounded-lg px-3 py-1.5 text-[12px]" style={chip(kind === k)}>
            {k === "all" ? "전체" : k === "theme" ? "테마" : "종목"}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="py-16 text-center" style={{ color: MUTED }}>불러오는 중...</div>
      ) : items.length === 0 ? (
        <EmptyState title="아직 남긴 관찰이 없습니다"
          hint={<><Link href="/radar" style={{ color: ACCENT }}>테마 레이더</Link>에서 테마를 펼쳐 &quot;흐름 이력 보기&quot;로 들어가거나,
            <Link href="/watchlist" style={{ color: ACCENT }}> 워치리스트</Link> 종목 상세에서 &quot;관찰 남기기&quot;를 눌러 첫 가설을 적어 보세요.</>} />
      ) : shown.length === 0 ? (
        <EmptyState title={`${TAB_LABEL[tab]} 관찰이 없습니다`} />
      ) : (
        <div className="space-y-3">
          {shown.map((o) => <ObservationCard key={o.id} o={o} currentWeek={currentWeek} onChanged={load} />)}
        </div>
      )}
    </div>
  );
}
