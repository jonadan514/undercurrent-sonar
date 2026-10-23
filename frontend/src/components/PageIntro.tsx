"use client";

import { useEffect, useState } from "react";
import { GLOSSARY } from "@/src/lib/glossary";
import { INTRO_STORAGE_PREFIX, PAGE_INTROS, type PageIntroKey } from "@/src/lib/pageIntros";
import Term from "@/src/components/Term";

// "이 화면은?" 상자(2026-10-23). 처음엔 펼쳐져 있고, 접으면 이 화면에서는 다음에도 접힌 채로.
// 저장은 브라우저(localStorage)에만 - 막힌 환경(사생활 모드 등)에서도 화면이 깨지지 않게 try/catch.
function readClosed(key: string): boolean {
  try { return window.localStorage.getItem(INTRO_STORAGE_PREFIX + key) === "1"; } catch { return false; }
}
function writeClosed(key: string, closed: boolean) {
  try {
    if (closed) window.localStorage.setItem(INTRO_STORAGE_PREFIX + key, "1");
    else window.localStorage.removeItem(INTRO_STORAGE_PREFIX + key);
  } catch { /* 저장 못 해도 이번 화면에서는 동작 */ }
}

export default function PageIntro({ k }: { k: PageIntroKey }) {
  const intro = PAGE_INTROS[k];
  // 서버 렌더와 첫 화면이 같도록 처음엔 접힌 상태로 그리고, 브라우저에서 저장값을 읽어 펼친다.
  const [closed, setClosed] = useState(true);
  const [ready, setReady] = useState(false);
  useEffect(() => { setClosed(readClosed(k)); setReady(true); }, [k]);

  const toggle = () => { setClosed((c) => { writeClosed(k, !c); return !c; }); };

  if (!ready) return null;
  if (closed) {
    return (
      <button type="button" onClick={toggle} className="mt-2 text-[12px] hover:underline" style={{ color: "var(--text-faint)" }}>
        ⓘ 이 화면은? (펼치기)
      </button>
    );
  }
  const rows: [string, string][] = [["무엇을", intro.what], ["언제", intro.when], ["할 일", intro.todo]];
  return (
    <div className="mt-3 max-w-[78ch] rounded-lg px-4 py-3 text-[13px] leading-relaxed"
         style={{ background: "rgba(255,176,32,0.06)", border: "1px solid rgba(255,176,32,0.22)" }}>
      <div className="flex items-start justify-between gap-3">
        <p className="font-bold" style={{ color: "var(--text-primary)" }}>이 화면은?</p>
        <button type="button" onClick={toggle} className="shrink-0 text-[12px] hover:underline" style={{ color: "var(--text-faint)" }}>
          접기
        </button>
      </div>
      <dl className="mt-1.5 grid grid-cols-[3.5rem_1fr] gap-x-3 gap-y-1">
        {rows.map(([label, text]) => (
          <div key={label} className="contents">
            <dt className="font-semibold" style={{ color: "#ffb020" }}>{label}</dt>
            <dd style={{ color: "var(--text-secondary)" }}>{text}</dd>
          </div>
        ))}
      </dl>
      {intro.terms && intro.terms.length > 0 && (
        <p className="mt-2 text-[12px]" style={{ color: "var(--text-muted)" }}>
          이 화면의 용어(눌러서 보기):{" "}
          {intro.terms.map((t, i) => (
            <span key={t}>{i > 0 && " · "}<Term k={t}>{GLOSSARY[t].term.split(" · ")[0]}</Term></span>
          ))}
          {" · "}<a href="/guide#glossary" className="underline" style={{ color: "var(--text-muted)" }}>용어 사전 전체</a>
        </p>
      )}
    </div>
  );
}
