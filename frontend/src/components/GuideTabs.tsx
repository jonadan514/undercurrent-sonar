"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// 가이드 세 화면 사이 이동 탭(2026-10-25 화면 통일). 예전엔 화면마다 이동 버튼 모양·위치가 달랐고
// (설명서는 큰 버튼 두 개, 실행 가이드는 "← 돌아가기", 세부 설명서는 없음) 지금 어디 있는지 안 보였다.
// 시장 탭(PageMarketTabs)과 같은 자리·모양.
const TABS = [
  { href: "/guide", label: "사용 설명서" },
  { href: "/guide/playbook", label: "투자 실행 가이드" },
  { href: "/guide/detail", label: "세부 설명서" },
];

export default function GuideTabs() {
  const pathname = usePathname();
  return (
    <nav className="mb-6 flex max-w-xl rounded-xl overflow-hidden" aria-label="가이드"
      style={{ border: "1px solid var(--border)", background: "var(--bg-inset)" }}>
      {TABS.map((t) => {
        const on = pathname === t.href;
        return (
          <Link key={t.href} href={t.href} aria-current={on ? "page" : undefined}
            className="flex flex-1 items-center justify-center py-2.5 text-[13px] font-bold transition-all whitespace-nowrap"
            style={{ background: on ? "#ffb020" : "transparent", color: on ? "#000" : "var(--text-muted)" }}>
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
