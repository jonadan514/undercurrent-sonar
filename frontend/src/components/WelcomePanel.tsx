"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Term from "@/src/components/Term";
import { WELCOME_STORAGE_KEY } from "@/src/lib/pageIntros";

// 첫 방문 안내(2026-10-23). 처음 들어온 사람에게 이 툴이 무엇이고 어디서 시작하는지 3단계로.
// "다시 보지 않기"를 누르면 이 브라우저에서는 접힌다(가이드의 "안내 다시 보기"로 되살림).
const STEPS: { title: string; body: React.ReactNode; href: string; cta: string }[] = [
  {
    title: "내 종목 소식 확인",
    body: <>주간 브리핑에서 관심 종목에 생긴 일(<Term k="disclosure">공시</Term>, 실적 발표, <Term k="insider_buy">내부자 매수</Term>)을 봅니다.</>,
    href: "/briefing", cta: "주간 브리핑",
  },
  {
    title: "움직이는 테마 찾기",
    body: <>테마 레이더에서 <Term k="axis">뉴스·실적·주가</Term> 중 실적이 먼저 좋아진 테마(<Term k="quiet_strength">조용한 강세</Term>)를 찾습니다.</>,
    href: "/radar", cta: "테마 레이더",
  },
  {
    title: "튼튼한 회사 좁혀 보기",
    body: <>워치리스트에서 그 테마의 <Term k="trap_filter">재무 필터 통과</Term> 종목을 싼 편·성장 순으로 좁혀 보고, 마음에 들면 메모와 함께 담습니다.</>,
    href: "/watchlist", cta: "워치리스트",
  },
];

export default function WelcomePanel() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    try { setShow(window.localStorage.getItem(WELCOME_STORAGE_KEY) !== "1"); } catch { setShow(true); }
  }, []);
  if (!show) return null;

  const close = () => {
    try { window.localStorage.setItem(WELCOME_STORAGE_KEY, "1"); } catch { /* 이번 화면에서만 닫힘 */ }
    setShow(false);
  };

  return (
    <section className="rounded-lg p-4 sm:p-5" style={{ background: "var(--bg-card)", border: "1px solid rgba(255,176,32,0.35)" }}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-[17px] font-bold" style={{ color: "var(--text-primary)" }}>처음 오셨나요?</h2>
          <p className="mt-1 max-w-[72ch] text-[13.5px] leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            U-Sonar는 <b>업황이 좋아지는 산업 테마를 먼저 찾고, 그 안에서 재무가 튼튼한 회사를 골라 보는</b> 주간 리서치 도구입니다.
            매주 월요일 아침에 새로 계산됩니다. <b>사라·팔라는 추천이나 종목 점수는 없습니다</b> - 사실을 보여주고 판단은 직접 합니다.
          </p>
        </div>
        <button type="button" onClick={close} className="shrink-0 text-[12px] hover:underline" style={{ color: "var(--text-faint)" }}>
          다시 보지 않기
        </button>
      </div>

      <ol className="mt-4 grid gap-2 sm:grid-cols-3">
        {STEPS.map((s, i) => (
          <li key={s.href} className="flex flex-col rounded-lg p-3" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
            <p className="text-[12px] font-bold" style={{ color: "#ffb020" }}>{i + 1}단계</p>
            <p className="mt-0.5 text-[14px] font-bold" style={{ color: "var(--text-primary)" }}>{s.title}</p>
            <p className="mt-1 flex-1 text-[13px] leading-relaxed" style={{ color: "var(--text-secondary)" }}>{s.body}</p>
            <Link href={s.href} className="mt-2 text-[13px] font-semibold hover:underline" style={{ color: "#ffb020" }}>
              {s.cta}로 가기 →
            </Link>
          </li>
        ))}
      </ol>

      <p className="mt-3 text-[12.5px]" style={{ color: "var(--text-muted)" }}>
        화면마다 맨 위 <b>"이 화면은?"</b>에 무엇을·언제·어떻게 보는지 적어 두었습니다. 점선 밑줄 용어는 누르면 뜻이 나옵니다.
        더 자세히는 <Link href="/guide" className="underline">사용 설명서</Link> ·{" "}
        <Link href="/guide/playbook" className="underline">투자 실행 가이드</Link>.
      </p>
    </section>
  );
}
