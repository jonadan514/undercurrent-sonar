import type { ReactNode } from "react";
import PageIntro from "@/src/components/PageIntro";
import type { PageIntroKey } from "@/src/lib/pageIntros";

// 화면 머리말 하나로(2026-10-21 외형 점검). 예전엔 제목 크기가 화면마다 14·18·22·24px·배지형으로 제각각이었다.
// 제목 + (앞 배지) + 기준일·갱신 주기(AsOf) + 한 줄 설명. 그 밖에 화면마다 필요한 것(버튼·출처 배지)은 children으로 아래에.
export default function PageHeader({ title, prefix, asOf, desc, intro, children }: {
  title: ReactNode;
  prefix?: ReactNode;   // 제목 앞 배지(예: 지수 이름)
  asOf?: ReactNode;     // <AsOf .../>
  desc?: ReactNode;
  intro?: PageIntroKey;  // "이 화면은?" 상자(src/lib/pageIntros.ts) - 처음 쓰는 사람 안내(2026-10-23)
  children?: ReactNode;
}) {
  return (
    <div className="mb-4">
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        {prefix}
        <h1 className="text-[20px] sm:text-[22px] font-bold" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>{title}</h1>
        {asOf}
      </div>
      {desc && <p className="mt-1 max-w-[68ch] text-[13.5px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{desc}</p>}
      {intro && <PageIntro k={intro} />}
      {children}
    </div>
  );
}

// 제목 앞 지수 배지(개요·섹터)
export function IndexBadge({ children }: { children: ReactNode }) {
  return (
    <span className="whitespace-nowrap text-[12px] font-bold px-2 py-0.5 rounded" style={{ background: "var(--border)", color: "var(--text-muted)" }}>
      {children}
    </span>
  );
}
