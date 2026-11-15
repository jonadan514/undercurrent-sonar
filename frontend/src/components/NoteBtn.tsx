"use client";

// 종목 관찰 노트 남기기 버튼(브리핑에서 옮김, 2026-11-15 테마 화면 '이 테마의 후보'와 같이 씀).
// 노트에는 누른 순간(오늘) 값이 기록된다 - 지난 브리핑에서 열면 그 사실을 창에 적는다.
import { useState } from "react";
import { ObservationForm } from "@/src/components/Observation";

export default function NoteBtn({ s, past }: { s: { market: string; symbol: string; name?: string | null }; past: boolean }) {
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  const title = s.market === "KR" ? `${s.name || s.symbol} (${s.symbol})` : `${s.symbol}${s.name ? ` · ${s.name}` : ""}`;
  return (
    <>
      <button onClick={() => setOpen(true)} className="text-[11px] px-1.5 rounded hover:brightness-125 whitespace-nowrap"
        style={{ color: saved ? "#4ade80" : "var(--text-muted)", border: `1px solid ${saved ? "#4ade8055" : "var(--border)"}` }}
        title="관찰 노트 남기기 - 4주·12주 뒤 그때와 지금을 대조">
        {saved ? "✓ 노트" : "✎ 노트"}
      </button>
      {open && (
        <ObservationForm kind="stock" market={s.market as "US" | "KR"} ticker={s.symbol} title={title}
          notice={past ? "지난 주 브리핑에서 열었지만, 노트에는 지금(오늘) 값이 기록됩니다." : undefined}
          onClose={() => setOpen(false)} onSaved={() => setSaved(true)} />
      )}
    </>
  );
}

