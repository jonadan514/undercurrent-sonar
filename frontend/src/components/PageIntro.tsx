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
  // 2026-10-25 사용자 의견: 상자가 78ch로 좁아 아래 칸들과 비율이 안 맞고 눈에 안 띈다 → 칸들과 같은 폭, 왼쪽 노란 띠,
  // 무엇을·언제·할 일을 PC에선 세 칸으로 나란히. 접힌 상태도 흐린 글자 대신 버튼 모양으로.
  if (closed) {
    return (
      <button type="button" onClick={toggle}
        className="mt-3 inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-semibold transition-colors hover:brightness-125"
        style={{ background: "rgba(255,176,32,0.08)", border: "1px solid rgba(255,176,32,0.35)", color: "#ffb020" }}>
        <span aria-hidden>💡</span>이 화면은? <span className="text-[11px]" aria-hidden>▼</span>
      </button>
    );
  }
  const rows: [string, string, string][] = [["👀", "무엇을", intro.what], ["🕐", "언제", intro.when], ["✅", "할 일", intro.todo]];
  return (
    <section className="mt-3 w-full rounded-xl px-4 py-3.5 sm:px-5" aria-label="이 화면은?"
      style={{ background: "rgba(255,176,32,0.07)", border: "1px solid rgba(255,176,32,0.32)", borderLeft: "4px solid #ffb020" }}>
      <div className="flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-[15px] font-bold" style={{ color: "#ffb020" }}>
          <span aria-hidden>💡</span>이 화면은?
        </p>
        <button type="button" onClick={toggle} className="shrink-0 rounded-md px-2 py-0.5 text-[12px] hover:brightness-125"
          style={{ color: "var(--text-muted)", border: "1px solid var(--border)" }}>
          접기 ▲
        </button>
      </div>
      <div className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-3">
        {rows.map(([icon, label, text]) => (
          <div key={label} className="rounded-lg px-3 py-2.5" style={{ background: "rgba(0,0,0,0.25)", border: "1px solid rgba(255,176,32,0.14)" }}>
            <p className="text-[12px] font-bold" style={{ color: "#ffb020" }}><span aria-hidden className="mr-1">{icon}</span>{label}</p>
            <p className="mt-1 text-[13.5px] leading-relaxed" style={{ color: "var(--text-primary)" }}>{text}</p>
          </div>
        ))}
      </div>
      {intro.terms && intro.terms.length > 0 && (
        <p className="mt-2.5 text-[12.5px]" style={{ color: "var(--text-secondary)" }}>
          이 화면의 용어(눌러서 보기):{" "}
          {intro.terms.map((t, i) => (
            <span key={t}>{i > 0 && " · "}<Term k={t}>{GLOSSARY[t].term.split(" · ")[0]}</Term></span>
          ))}
          {" · "}<a href="/guide#glossary" className="underline" style={{ color: "var(--text-muted)" }}>용어 사전 전체</a>
        </p>
      )}
    </section>
  );
}
