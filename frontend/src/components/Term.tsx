"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { GLOSSARY, type GlossaryKey } from "@/src/lib/glossary";

// 어려운 용어에 점선 밑줄을 긋고, 누르면(휴대폰) 또는 마우스를 올리면 용어 사전 설명을 띄운다.
// 설명은 src/lib/glossary.ts 한 곳에서만 - 화면마다 같은 말이 다르게 쓰이지 않게(2026-10-23).
export default function Term({ k, children }: { k: GlossaryKey; children?: ReactNode }) {
  const entry = GLOSSARY[k];
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("touchstart", close);
    };
  }, [open]);

  if (!entry) return <>{children}</>;
  return (
    <span ref={ref} className="relative inline-block" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen((v) => !v); }}
        className="cursor-help underline decoration-dotted underline-offset-[3px] focus:outline-none focus-visible:ring-1 focus-visible:ring-[#ffb020]"
        style={{ textDecorationColor: "var(--text-faint)", color: "inherit", font: "inherit" }}
        aria-expanded={open}
      >
        {children ?? entry.term}
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-0 top-full z-[60] mt-1.5 block w-[min(300px,80vw)] rounded-lg p-3 text-left text-[12.5px] font-normal leading-relaxed shadow-xl"
          style={{ background: "#111009", border: "1px solid #262112", color: "#c9c2ae", letterSpacing: 0, whiteSpace: "normal" }}
        >
          <span className="block font-bold" style={{ color: "#ece7d8" }}>{entry.term}</span>
          <span className="mt-1 block">{entry.short}</span>
          {entry.use && <span className="mt-1.5 block" style={{ color: "#8b8271" }}>{entry.use}</span>}
        </span>
      )}
    </span>
  );
}
