"use client";

import { usePathname } from "next/navigation";
import { useMarket } from "@/src/contexts/MarketContext";
import US from "country-flag-icons/react/3x2/US";
import KR from "country-flag-icons/react/3x2/KR";

// 시장(미국/한국) 구분이 있는 페이지에서만 탭 노출
// 성적표도 시장별 화면인데 빠져 있어 다른 화면에서 바꾸고 와야 했다(2026-10-21 외형 점검)
const MARKET_PAGES = ["/sector", "/radar", "/quarterly", "/scorecard"];

export default function PageMarketTabs() {
  const pathname = usePathname();
  const { market, setMarket } = useMarket();

  // 개요("/")는 2026-10-25부터 두 시장을 한 장에 단락으로 보여 줘서 탭이 없다
  const show = MARKET_PAGES.some((p) => pathname.startsWith(p));
  if (!show) return null;

  const tabs = [
    { key: "US" as const, label: "미국 시장", Flag: US },
    { key: "KR" as const, label: "한국 시장", Flag: KR },
  ];

  return (
    <div
      className="mb-6 flex max-w-md rounded-xl overflow-hidden"
      style={{ border: "1px solid var(--border)", background: "var(--bg-inset)" }}
    >
      {tabs.map(({ key, label, Flag }) => (
        <button
          key={key}
          onClick={() => setMarket(key)}
          className="flex flex-1 items-center justify-center gap-2 py-2.5 text-[13px] font-bold transition-all"
          style={{
            background: market === key ? "#ffb020" : "transparent",
            color:      market === key ? "#000" : "var(--text-muted)",
            cursor:     "pointer",
          }}
        >
          <Flag style={{ width: 20, height: "auto", borderRadius: 2 }} />
          {label}
        </button>
      ))}
    </div>
  );
}
