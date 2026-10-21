import type { ReactNode } from "react";

// 빈 상태 한 모양(2026-10-21 외형 점검 3). 예전엔 점선 상자·카드 안 글·가운데 글이 화면마다 달랐다.
// 무엇이 없는지(title) + 언제 생기는지·어떻게 채우는지(hint).
export default function EmptyState({ title, hint, className = "" }: { title: ReactNode; hint?: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl px-4 py-5 text-center ${className}`}
      style={{ border: "1px dashed var(--border-ctrl)", background: "var(--bg-inset)" }}>
      <p className="text-[13.5px] font-semibold" style={{ color: "var(--text-secondary)" }}>{title}</p>
      {hint && <p className="mt-1 text-[12.5px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{hint}</p>}
    </div>
  );
}
