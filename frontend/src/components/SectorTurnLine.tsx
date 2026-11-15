"use client";

// 업종 흐름 한 줄(2026-11-15, 사용자: 사용성 3번 - 섹터 분석 화면은 잘 안 본다).
// 섹터 분석(/sector)의 '전환 중인 섹터'와 같은 규칙: 3달 상대강도와 1달 상대강도의 부호가 다른 업종.
// 개요 시장 환경 칸 아래에 미국·한국 한 줄씩 - 판정이 아니라 조건에 맞는 업종 이름만. 자세한 건 /sector(메뉴에서는 뺐다).
import { useEffect, useState } from "react";
import { sectorKo } from "@/src/lib/sectorNames";

type Row = { sector?: string; ticker?: string; name?: string; rs_3m?: number | null; rs_1m?: number | null };
type Turn = { up: string[]; down: string[]; date?: string };

function turns(d: Record<string, unknown> | null, kr: boolean): Turn | null {
  if (!d) return null;
  const rows = ((kr ? d.sector_data : d.etf_data) ?? []) as Row[];
  const name = (r: Row) => (kr ? r.sector ?? "" : sectorKo(r.name ?? r.ticker ?? ""));
  const pick = (dir: "up" | "down") => rows
    .filter((r) => r.rs_3m != null && r.rs_1m != null && (dir === "up" ? r.rs_3m! < 0 && r.rs_1m! > 0 : r.rs_3m! > 0 && r.rs_1m! < 0))
    .sort((a, b) => (dir === "up" ? b.rs_1m! - a.rs_1m! : a.rs_1m! - b.rs_1m!))
    .slice(0, 3).map(name);
  return { up: pick("up"), down: pick("down"), date: d.date as string | undefined };
}

export default function SectorTurnLine() {
  const [t, setT] = useState<{ US: Turn | null; KR: Turn | null } | null>(null);
  useEffect(() => {
    Promise.all([
      fetch("/api/data/sector").then((r) => r.json()).catch(() => null),
      fetch("/api/data/kr/sector").then((r) => r.json()).catch(() => null),
    ]).then(([us, kr]) => setT({ US: turns(us, false), KR: turns(kr, true) }));
  }, []);
  if (!t || (!t.US && !t.KR)) return null;
  const line = (flag: string, x: Turn | null) => x && (
    <p className="text-[13px]" style={{ color: "var(--text-secondary)" }}>
      <span className="mr-1">{flag}</span>
      <span style={{ color: "#4ade80" }}>↗ 돌아서는 중</span> {x.up.length ? x.up.join(" · ") : "없음"}
      <span className="mx-1.5" style={{ color: "var(--text-faint)" }}>|</span>
      <span style={{ color: "#f87171" }}>↘ 꺾이는 중</span> {x.down.length ? x.down.join(" · ") : "없음"}
    </p>
  );
  return (
    <div className="mt-3 pt-2.5 space-y-1" style={{ borderTop: "1px solid var(--border)" }}>
      <p className="text-[12.5px] font-bold" style={{ color: "var(--text-primary)" }}>
        업종 흐름 <span className="font-normal" style={{ color: "var(--text-muted)" }}>- 3달은 시장보다 약(강)했는데 최근 1달 강(약)해진 업종 · 매주 화요일</span>
      </p>
      {line("🇺🇸", t.US)}
      {line("🇰🇷", t.KR)}
      <a href="/sector" className="text-[12px] hover:underline" style={{ color: "var(--text-muted)" }}>업종 상대강도 자세히 →</a>
    </div>
  );
}
