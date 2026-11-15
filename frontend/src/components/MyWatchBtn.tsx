"use client";

// '⭐ 관심 담기' 한 번 누르기(2026-11-15, 사용자: 사용성 B). 브리핑 🎯 후보 줄·기업 카드에서 바로 내 워치리스트에 담는다 -
// 담은 종목은 다음 주부터 브리핑 ⭐ 칸에서 실적 발표·공시·내부자 매수가 따라온다. 빼기는 워치리스트 화면에서(실수로 빠지지 않게).
import { useEffect, useState } from "react";

let cache: Promise<Set<string>> | null = null;   // 한 화면에 버튼이 여럿이어도 목록은 한 번만 읽는다
function myKeys(): Promise<Set<string>> {
  cache ??= fetch("/api/watchlist/my").then((r) => r.json())
    .then((rows) => new Set<string>((Array.isArray(rows) ? rows : []).map((x: { market: string; symbol: string }) => `${x.market}:${x.symbol}`)))
    .catch(() => new Set<string>());
  return cache;
}

export default function MyWatchBtn({ market, symbol, name, size = "sm" }: { market: string; symbol: string; name?: string | null; size?: "sm" | "md" }) {
  const key = `${market}:${symbol.toUpperCase()}`;
  const [state, setState] = useState<"loading" | "in" | "out" | "saving">("loading");
  useEffect(() => { myKeys().then((s) => setState(s.has(key) ? "in" : "out")); }, [key]);
  const add = async () => {
    setState("saving");
    try {
      const r = await fetch("/api/watchlist/my", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ market, symbol, name: name ?? null }) });
      if (!r.ok) throw new Error();
      (await myKeys()).add(key);
      setState("in");
    } catch { setState("out"); }
  };
  const cls = size === "md" ? "text-[12.5px] px-2.5 py-1" : "text-[12px] px-2 py-0.5";
  if (state === "loading") return null;
  if (state === "in") {
    return <a href="/watchlist" className={`${cls} rounded whitespace-nowrap hover:brightness-125`} title="내 워치리스트에 있음 - 빼기는 워치리스트 화면에서"
      style={{ background: "#ffb02022", color: "#ffb020" }}>⭐ 관심 중</a>;
  }
  return (
    <button onClick={add} disabled={state === "saving"} className={`${cls} rounded whitespace-nowrap hover:brightness-125`}
      title="내 워치리스트에 담기 - 다음 주부터 브리핑 ⭐ 칸에서 실적 발표·공시·내부자 매수가 따라옵니다"
      style={{ border: "1px solid #ffb02066", color: "#ffb020" }}>{state === "saving" ? "담는 중…" : "☆ 관심 담기"}</button>
  );
}
