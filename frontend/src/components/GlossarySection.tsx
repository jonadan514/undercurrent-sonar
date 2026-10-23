"use client";

import { useState } from "react";
import { GLOSSARY, GLOSSARY_GROUPS } from "@/src/lib/glossary";
import { INTRO_STORAGE_PREFIX, WELCOME_STORAGE_KEY } from "@/src/lib/pageIntros";

// 가이드의 "용어 사전" 칸(2026-10-23) - 화면 곳곳의 점선 밑줄 용어와 같은 설명(src/lib/glossary.ts)을 한 번에.
// 아래 "안내 다시 보기"는 접어 둔 "이 화면은?" 상자와 첫 화면 안내를 모두 되살린다.
export default function GlossarySection() {
  const [reset, setReset] = useState(false);
  const entries = Object.entries(GLOSSARY);

  const resetIntros = () => {
    try {
      const keys: string[] = [];
      for (let i = 0; i < window.localStorage.length; i++) {
        const k = window.localStorage.key(i);
        if (k && (k.startsWith(INTRO_STORAGE_PREFIX) || k === WELCOME_STORAGE_KEY)) keys.push(k);
      }
      keys.forEach((k) => window.localStorage.removeItem(k));
    } catch { /* 저장소를 못 쓰는 환경 - 안내는 원래 매번 보인다 */ }
    setReset(true);
  };

  return (
    <section id="glossary" className="scroll-mt-20 rounded-lg p-4 sm:p-5" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-[17px] font-bold" style={{ color: "var(--text-primary)" }}>📖 용어 사전</h2>
          <p className="mt-1 text-[13px]" style={{ color: "var(--text-muted)" }}>
            화면에서 점선 밑줄 친 용어와 같은 설명입니다. 투자 공부 없이 읽을 수 있게 썼습니다.
          </p>
        </div>
        <button type="button" onClick={resetIntros} className="shrink-0 rounded-lg px-3 py-1.5 text-[12px] font-semibold"
                style={{ background: "var(--bg-inset)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
          {reset ? "✓ 안내를 다시 켰습니다" : "접어 둔 안내 다시 보기"}
        </button>
      </div>

      {GLOSSARY_GROUPS.map((g) => {
        const items = entries.filter(([, e]) => e.group === g);
        if (!items.length) return null;
        return (
          <div key={g} className="mt-5">
            <h3 className="text-[13px] font-bold" style={{ color: "#ffb020" }}>{g}</h3>
            <dl className="mt-2 grid gap-2 md:grid-cols-2">
              {items.map(([k, e]) => (
                <div key={k} className="rounded-lg p-3" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                  <dt className="text-[13.5px] font-bold" style={{ color: "var(--text-primary)" }}>{e.term}</dt>
                  <dd className="mt-1 text-[13px] leading-relaxed" style={{ color: "var(--text-secondary)" }}>{e.short}</dd>
                  {e.use && <dd className="mt-1 text-[12.5px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{e.use}</dd>}
                </div>
              ))}
            </dl>
          </div>
        );
      })}
    </section>
  );
}
