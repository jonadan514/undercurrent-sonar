import type { ReactNode } from "react";

// 칸 아래 기준·출처 설명(2026-10-21 외형 점검 3). 기능을 붙일 때마다 칸 아래에 회색 11px 설명이 늘어 화면이 빽빽했다 -
// 기본은 접어 두고 "ⓘ 기준"을 누르면 12px로 펼친다. 짧은 사실(목록은 30건까지 등)은 접지 않고 그대로 둔다.
export default function Note({ children, label = "기준·출처" }: { children: ReactNode; label?: string }) {
  return (
    <details className="mt-1.5 group">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-[12px] select-none" style={{ color: "var(--text-faint)" }}>
        <span aria-hidden>ⓘ</span>{label}<span className="transition-transform group-open:rotate-90" aria-hidden>›</span>
      </summary>
      <p className="mt-1 text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{children}</p>
    </details>
  );
}
