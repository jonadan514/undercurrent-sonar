"use client";

import { useEffect, useState } from "react";
import InfoTooltip from "@/src/components/InfoTooltip";

// 데이터 상태 한눈에 보기(2026-10-21) - 정기 수집마다 마지막 저장 시각과 허용 기간. 사이드바 아래 칸을 누르면 온다.
// 각 표의 마지막 저장 시각으로 본다(GitHub 실행 기록 아님) - 실행은 됐는데 저장이 안 된 것도 지연으로 보인다.
type Item = { key: string; label: string; group: "매일" | "매주" | "분기"; cadence: string; ok_days: number; note: string | null;
  last: string | null; age_days: number | null; status: "ok" | "late" | "missing" };
type Health = { checked_at: string; summary: { total: number; ok: number; late: number; missing: number }; items: Item[] };

const STATUS = {
  ok: { label: "정상", color: "#4ade80" },
  late: { label: "지연", color: "#facc15" },
  missing: { label: "없음", color: "#f87171" },
} as const;

// KST로 'MM/DD HH:mm'
function kst(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(new Date(iso).getTime() + 9 * 3_600_000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getUTCMonth() + 1)}/${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}
function ago(days: number | null): string {
  if (days == null) return "-";
  if (days < 1) return `${Math.max(1, Math.round(days * 24))}시간 전`;
  return `${Math.floor(days)}일 전`;
}

export default function StatusPage() {
  const [h, setH] = useState<Health | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    fetch("/api/data/health").then((r) => r.json()).then(setH).catch(() => setErr(true));
  }, []);

  return (
    <div className="space-y-2">
      <div className="bg-card rounded-xl p-3">
        <div className="flex items-center gap-2 mb-1">
          <h1 className="text-[18px] font-black" style={{ color: "var(--text-primary)" }}>데이터 상태</h1>
          <InfoTooltip content="정기 수집마다 표에 마지막으로 저장된 시각입니다. 허용 기간보다 오래되면 '지연' - GitHub 예약 실행은 몇 시간씩 늦게 시작되기도 해서 여유를 두었습니다. 표가 아직 없거나 비어 있으면 '없음'." />
        </div>
        <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>
          {err ? "불러오지 못했습니다." : !h ? "확인 중…" :
            `${kst(h.checked_at)} 확인 · ${h.summary.total}개 중 정상 ${h.summary.ok}${h.summary.late ? ` · 지연 ${h.summary.late}` : ""}${h.summary.missing ? ` · 없음 ${h.summary.missing}` : ""} · 시각은 한국 시간`}
        </p>
      </div>

      {h && (["매일", "매주", "분기"] as const).map((g) => {
        const rows = h.items.filter((x) => x.group === g);
        if (rows.length === 0) return null;
        return (
          <div key={g} className="bg-card rounded-xl p-3">
            <h2 className="stat-label mb-2">{g} 갱신</h2>
            <div className="space-y-1">
              {rows.map((x) => {
                const st = STATUS[x.status];
                return (
                  <div key={x.key} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 rounded-lg px-3 py-2 text-[13px]"
                    style={{ background: "var(--bg-inset)", border: `1px solid ${x.status === "ok" ? "var(--border)" : st.color + "55"}` }}>
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: st.color }} />
                    <span className="font-semibold min-w-[11rem]" style={{ color: "var(--text-primary)" }}>{x.label}</span>
                    <span className="text-[12px] min-w-[6rem]" style={{ color: "var(--text-muted)" }}>{x.cadence}</span>
                    <span className="font-mono text-[12px]" style={{ color: "var(--text-secondary)" }}>{kst(x.last)}</span>
                    <span className="font-mono text-[12px]" style={{ color: st.color }}>{x.status === "missing" ? "없음" : `${ago(x.age_days)} · ${st.label}`}</span>
                    <span className="text-[11px] sm:ml-auto" style={{ color: "var(--text-faint)" }}>
                      허용 {x.ok_days}일{x.note ? ` · ${x.note}` : ""}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      <p className="text-[11px] px-1" style={{ color: "var(--text-faint)" }}>
        지연이 보이면 그 칸의 화면 숫자가 오래된 것입니다. 정기 실행이 실패하면 텔레그램 알림도 갑니다. 공시·내부자·8-K는 새 공시가 없는 날엔 시각이 바뀌지 않아 허용 기간을 길게 두었습니다.
      </p>
    </div>
  );
}
