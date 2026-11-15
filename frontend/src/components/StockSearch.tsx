"use client";

// 메뉴 맨 위 종목 찾기(2026-11-15, 사용자: 사용성 C - PC로 가끔 들어와 '이 회사 어떤가' 볼 때 가장 빠른 길).
// 이름·코드를 치면 /api/search 결과, 누르거나 Enter면 기업 카드(/company)로.
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type Hit = { market: "US" | "KR"; symbol: string; name: string };

export default function StockSearch({ onGo }: { onGo?: () => void }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [sel, setSel] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (!q.trim()) { setHits([]); return; }
    timer.current = setTimeout(() => {
      fetch(`/api/search?q=${encodeURIComponent(q.trim())}`).then((r) => r.json())
        .then((d) => { setHits(Array.isArray(d.items) ? d.items : []); setSel(0); }).catch(() => setHits([]));
    }, 150);
  }, [q]);
  const go = (h: Hit | undefined) => {
    if (!h) return;
    setQ(""); setHits([]);
    router.push(`/company?stock=${h.market}:${encodeURIComponent(h.symbol)}`);
    onGo?.();
  };
  return (
    // zIndex는 인라인으로 - 아래 메뉴 링크(relative)가 결과 목록 위에 그려졌고, z-30·z-50 클래스는 이 프로젝트 CSS에 생성되지 않았다
    <div className="relative px-3 pt-3" style={{ zIndex: 30 }}>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="🔍 종목 찾기 (이름·코드)" aria-label="종목 찾기"
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, hits.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
          else if (e.key === "Enter") go(hits[sel]);
          else if (e.key === "Escape") { setQ(""); setHits([]); }
        }}
        className="w-full rounded-lg px-2.5 py-1.5 text-[13px] outline-none"
        style={{ background: "var(--bg-inset)", border: "1px solid var(--border-ctrl, #453b1f)", color: "var(--text-primary)" }} />
      {hits.length > 0 && (
        <div className="absolute left-3 right-3 mt-1 overflow-hidden rounded-lg shadow-lg"
          style={{ zIndex: 50, background: "#14120b", border: "1px solid #453b1f" }}>
          {hits.map((h, i) => (
            <button key={`${h.market}:${h.symbol}`} onMouseDown={(e) => { e.preventDefault(); go(h); }} onMouseEnter={() => setSel(i)}
              className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[12.5px]"
              style={{ background: i === sel ? "rgba(255,176,32,0.12)" : "transparent", color: "var(--text-primary)" }}>
              <span>{h.market === "KR" ? "🇰🇷" : "🇺🇸"}</span>
              <span className="truncate font-semibold">{h.market === "KR" ? h.name : h.symbol}</span>
              <span className="ml-auto shrink-0 text-[11px]" style={{ color: "var(--text-muted)" }}>{h.market === "KR" ? h.symbol : h.name.slice(0, 18)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
