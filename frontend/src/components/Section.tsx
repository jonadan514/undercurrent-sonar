import type { CSSProperties, ReactNode } from "react";
import { Children } from "react";
import InfoTooltip from "@/src/components/InfoTooltip";

// 화면 구조 공용 부품(2026-10-25 화면 통일). 예전엔 칸 제목이 화면마다 회색 12~13px(개요·성적표)·흰 14px(섹터·브리핑)·
// 15px(테마 상세)로 제각각이고, 요약 숫자 칸도 워치리스트(둥근 카드)·레이더(이어 붙인 칸)·개요(카드 안 칸) 모양이 달랐다.
// 모든 화면이 같은 순서로 읽히게: 머리말(PageHeader) → 요약 숫자(StatGrid) → 칸(Section)들, 비슷한 칸은 GroupTitle 아래.

type Tone = "mine" | "warm";
const TONE_BOX: Record<Tone, CSSProperties> = {
  mine: { background: "#f59e0b0d", border: "1px solid #f59e0b44" },
  warm: { background: "#ffb02008", border: "1px solid #ffb02022" },
};
const TONE_HEAD: Record<Tone, string> = { mine: "#f59e0b", warm: "#ffb020" };

// 칸 하나 = 카드 + 제목 줄(제목 · 건수 · ⓘ · 보조 설명 · 오른쪽 링크·버튼)
export function Section({ id, title, count, info, sub, right, tone, className = "", children }: {
  id?: string;
  title: ReactNode;
  count?: ReactNode;
  info?: ReactNode;      // ⓘ 툴팁 내용
  sub?: ReactNode;       // 제목 옆 보조 설명(기준일·출처 등 짧게)
  right?: ReactNode;     // 오른쪽 끝(전체 보기 링크, 기간 선택 등)
  tone?: Tone;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <section id={id} className={`rounded-xl p-3 sm:p-4 ${tone ? "" : "bg-card"} ${className}`}
      style={tone ? TONE_BOX[tone] : { border: "1px solid var(--border)" }}>
      <div className={`flex flex-wrap items-baseline gap-x-2 gap-y-0.5 ${children ? "mb-2.5" : ""}`}>
        <h2 className="text-[15px] font-bold" style={{ color: tone ? TONE_HEAD[tone] : "var(--text-primary)" }}>{title}</h2>
        {count != null && <span className="text-[13px] font-bold" style={{ color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>{count}</span>}
        {info && <span className="self-center"><InfoTooltip content={info} /></span>}
        {sub && <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>{sub}</span>}
        {right && <span className="ml-auto self-center text-[12px]">{right}</span>}
      </div>
      {children}
    </section>
  );
}

// 비슷한 칸 묶음 제목. 안에 보여 줄 칸이 하나도 없으면 제목도 숨긴다.
export function GroupTitle({ title, children }: { title: string; children: ReactNode }) {
  const kids = Children.toArray(children);
  if (kids.length === 0) return null;
  return (
    <div className="space-y-2">
      <h2 className="stat-label px-1 pt-3">{title}</h2>
      {kids}
    </div>
  );
}

// 요약 숫자 칸. href가 있으면 누르면 그 목록으로, onClick이 있으면 버튼(필터 등), 없으면 표시만.
export function StatTile({ label, value, sub, href, onClick, active, emphasis, hint }: {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  href?: string;
  onClick?: () => void;
  active?: boolean;       // 지금 켜진 필터
  emphasis?: "accent" | "good";   // 먼저 볼 숫자(예: 이번 회차 신규)
  hint?: string;
}) {
  const color = emphasis === "good" ? "#4ade80" : emphasis === "accent" ? "var(--accent, #ffb020)" : "var(--num, #ffb020)";
  const box: CSSProperties = {
    background: active ? "#ffb02012" : "var(--bg-inset)",
    border: `1px solid ${active ? "#ffb02066" : emphasis === "good" ? "#4ade8055" : "var(--border)"}`,
  };
  const inner = (
    <>
      <p className="text-[12px] truncate" style={{ color: "var(--text-muted)" }}>{label}</p>
      <p className="text-[22px] font-bold leading-tight mt-0.5" style={{ color, fontVariantNumeric: "tabular-nums" }}>{value}</p>
      {sub && <p className="text-[12px] mt-0.5 truncate" style={{ color: "var(--text-secondary)" }}>{sub}</p>}
    </>
  );
  const cls = "rounded-lg px-3 py-2.5 block text-left w-full";
  if (href) return <a href={href} className={`${cls} transition-colors hover:brightness-125`} style={box} title={hint}>{inner}</a>;
  if (onClick) return <button type="button" onClick={onClick} className={`${cls} transition-colors hover:brightness-125`} style={box} title={hint} aria-pressed={active}>{inner}</button>;
  return <div className={cls} style={box} title={hint}>{inner}</div>;
}

export function StatGrid({ children, cols = 4 }: { children: ReactNode; cols?: 3 | 4 | 5 | 6 }) {
  const lg = { 3: "lg:grid-cols-3", 4: "lg:grid-cols-4", 5: "lg:grid-cols-5", 6: "lg:grid-cols-6" }[cols];
  return <div className={`grid grid-cols-2 sm:grid-cols-3 ${lg} gap-2`}>{children}</div>;
}
