"use client";

import { usePathname } from "next/navigation";
import DailyQuote from "@/src/components/DailyQuote";

// 맨 위 띠(2026-10-21 외형 점검): 명언은 개요에만. 다른 화면은 PC에선 띠를 없애고(세로 80px 절약),
// 휴대폰에선 메뉴 버튼 자리만 남긴 얇은 띠.
export default function TopBar() {
  const pathname = usePathname();
  if (pathname === "/") {
    return (
      // 명언은 넓은 화면(lg)에서만 보인다 - 그보다 좁으면 휴대폰은 메뉴 버튼 띠(h-14), 태블릿은 띠 없음
      <header className="flex h-14 md:hidden lg:flex lg:h-20 shrink-0 items-center gap-4 border-b px-4 pl-14 lg:pl-4" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
        <DailyQuote />
      </header>
    );
  }
  return <header className="h-14 shrink-0 border-b md:hidden" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }} />;
}
