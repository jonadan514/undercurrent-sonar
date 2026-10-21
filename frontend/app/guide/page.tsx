"use client";

import Link from "next/link";
import PageHeader from "@/src/components/PageHeader";

const GUIDE_SECTIONS = [
  { href: "/",           icon: "⊡", label: "개요",        desc: "접속 시작점. 맨 위 \"이번 주 변화\" 칸(후보·실적 반전·실적 발표·한국 공시·내부자 매수·노트 회고)을 누르면 해당 목록으로. 매크로 카드는 1년 그래프·범위까지." },
  { href: "/briefing",   icon: "📋", label: "주간 브리핑", desc: "매주 월요일 아침 자동 생성. 맨 위 ⭐ 관심 종목에 생긴 일(내 관심·노트 종목만 모음) → 지난주 시장·수급·매크로 → 워치리스트·실적 반전 → 실적 발표 → 한국 공시·미국 8-K → 내부자 매수(관심 종목 / 🆕 관심 밖 새 이름). 위 목차로 칸 이동." },
  { href: "/sector",     icon: "⊞", label: "섹터 분석",   desc: "지금 강한 업종과 방향이 바뀌는 업종 확인. 어느 분야를 들여다볼지 방향을 잡는 탭. 한국은 코스피200 섹터지수, 미국은 SPDR 11개 ETF 기준." },
  { href: "/radar",      icon: "📡", label: "테마 레이더", desc: "미국·한국 산업 테마를 뉴스·실적·주가 세 축으로 매주 관찰. 종합 점수 없이, 정해진 조합에만 라벨을 붙임. 상단 탭으로 시장 전환." },
  { href: "/quarterly",  icon: "🔍", label: "분기 리서치", desc: "테마 레이더보다 한 단계 더 들어가, 분기 재무가 실제로 움직였는지와 뉴스 반응을 나눠서 본다. \"재무는 이미 움직였는데 뉴스는 조용한\" 테마를 찾는 화면." },
  { href: "/watchlist",  icon: "🔖", label: "워치리스트",  desc: "재무 건전성 필터를 통과한 후보를 순위 없이 리스트업(주간 갱신). 밸류(싼가)·성장(자라는가) 축, 검색창까지 지원. 종목 클릭 시 재무 지표 + 뉴스 기반 네러티브 브리프 + 정성 체크리스트 + 메모까지 한 팝업에서." },
  { href: "/scorecard",  icon: "📈", label: "성적표",      desc: "과거 워치리스트 후보에 실제 주가를 대조한 사후 검증. 아래 \"신호 사후 확인\"은 브리핑·레이더 신호가 4·12주 뒤 유니버스·지수보다 어땠는지(분포만)." },
  { href: "/status",     icon: "🩺", label: "데이터 상태", desc: "정기 수집 20개의 마지막 저장 시각과 정상·지연·없음. 사이드바 맨 아래 칸을 누르면 열림." },
];

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[12px] font-bold uppercase tracking-widest mb-2" style={{ color: "var(--text-muted)" }}>
      {children}
    </h2>
  );
}
function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`bg-card rounded-xl p-5 ${className}`}>{children}</div>;
}
function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span className="inline-block px-2 py-0.5 rounded-lg text-[12px] font-bold"
      style={{ background: `${color}22`, color, border: `1px solid ${color}44` }}>
      {text}
    </span>
  );
}

export default function GuidePage() {
  return (
    <div className="space-y-6 max-w-5xl">

      {/* Header */}
      <div>
        <PageHeader title="사용 설명서" desc="미국(S&P 500·400) · 한국(시총 3000억+) 개인 투자자용 테마·재무 리서치 대시보드" />
        <div className="flex flex-wrap gap-2 mt-3">
          <Link
            href="/guide/playbook"
            className="inline-flex items-center gap-1.5 text-[12px] font-semibold rounded-xl px-3 py-1.5 transition-colors"
            style={{ background: "#ffb02018", border: "1px solid #ffb02044", color: "#ffb020" }}
          >
            ▶ 투자 실행 가이드 — 발굴부터 매도까지 →
          </Link>
          <Link
            href="/guide/detail"
            className="inline-flex items-center gap-1.5 text-[12px] font-semibold rounded-xl px-3 py-1.5 transition-colors"
            style={{ background: "var(--bg-inset)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}
          >
            <span style={{ color: "#ffb020" }}>◉</span>
            각 기능의 원리·해석법 세부 설명서 보기 →
          </Link>
        </div>
      </div>

      {/* ── 완전 초보자 시작 가이드 ── */}
      <Card>
        <SectionTitle>📌 처음이라면 — 4단계로 좁혀가기</SectionTitle>
        <p className="text-[12px] mb-4 leading-relaxed" style={{ color: "var(--text-muted)" }}>
          Undercurrent Sonar는 <span className="text-white font-semibold">"매수하라"고 말해주는 도구가 아닙니다.</span> 대신
          "지금 뭘 눈여겨봐야 하는가"를 테마 → 업종 맥락 → 분기 재무 → 개별 종목 순서로 좁혀가도록 만들어졌습니다.
          투자가 처음이라면 아래 4단계를 순서대로 따라가 보세요. 각 단계는 서로 다른 화면(탭)입니다.
        </p>
        <div className="space-y-2 mb-5">
          {[
            {
              step: "STEP 1", color: "#ffb020",
              title: "어떤 테마가 움직이나? → 테마 레이더",
              body: "AI 반도체·데이터센터 전력 같은 세부 산업 테마를 뉴스·실적·주가 세 축으로 봅니다. 특히 \"Quiet Strength\"(펀더멘털이 먼저 - 시장이 아직 안 움직임) 라벨이 붙은 테마를 눈여겨보세요. 뉴스만 봐서는 찾을 수 없는, 이 도구가 존재하는 이유입니다. 테마 줄의 📄 표시는 최근 7일 소속 기업의 공시(공급계약·8-K 등)와 내부자 장내 매수 건수입니다 — 세 축과 별개로, 실적 축보다 먼저 보이는 회사 쪽 움직임입니다.",
            },
            {
              step: "STEP 2", color: "#facc15",
              title: "업종 전체 흐름은 어떤가? → 섹터 분석",
              body: "업종별 상대강도와 방향이 바뀌는 업종(3달 대비 최근 1달)을 보여줍니다. 테마 레이더에서 눈에 띈 테마가 속한 업종이 지금 강한지 약한지, 큰 흐름과 같은 방향인지 맥락을 확인하는 화면입니다.",
            },
            {
              step: "STEP 3", color: "#6fb3b8",
              title: "정말 재무로 뒷받침되나? → 분기 리서치",
              body: "테마 레이더가 큰 그림이라면, 분기 리서치는 그 테마 소속 기업들의 분기 재무가 실제로 개선됐는지를 확인합니다. \"조용한 변화\"(재무는 움직였는데 뉴스는 아직 조용함)에 있는 테마가 가장 먼저 볼 가치가 있는 자리입니다.",
            },
            {
              step: "STEP 4", color: "#4ade80",
              title: "그 안에서 어떤 종목을 살까? → 워치리스트",
              body: "재무 건전성 필터를 통과한 후보 중에서 밸류(싼가)와 성장(자라는가)을 같이 봅니다. 종목을 클릭하면 뉴스 기반 요약과 정성 체크리스트·메모까지 그 자리에서 남길 수 있어요. 1~3년 보유를 전제로 한 도구이니 최종 선택은 항상 본인의 판단입니다.",
            },
          ].map(({ step, color, title, body }) => (
            <div key={step} className="rounded-xl p-4" style={{ background: "var(--bg-inset)", border: `1px solid ${color}33` }}>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-[12px] font-black px-2 py-0.5 rounded" style={{ background: `${color}22`, color }}>{step}</span>
                <p className="text-[13px] font-bold text-white">{title}</p>
              </div>
              <p className="text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{body}</p>
            </div>
          ))}
        </div>

        <div className="rounded-xl p-4 mb-3" style={{ background: "#6fb3b808", border: "1px solid #6fb3b822" }}>
          <p className="text-[12px] font-bold" style={{ color: "#6fb3b8" }}>💡 4단계를 다 거칠 필요는 없습니다</p>
          <p className="text-[12px] mt-1 leading-relaxed" style={{ color: "var(--text-muted)" }}>
            시간이 없다면 워치리스트만 봐도 됩니다 — 재무 건전성 필터를 이미 통과한 종목만 모아둔 화면이라
            그 자체로 완결된 출발점입니다. 테마 레이더·섹터 분석·분기 리서치는 "왜 지금 이 종목인가"에 대한
            맥락을 더 깊이 알고 싶을 때 순서대로 참고하면 됩니다.
          </p>
        </div>

        <div className="rounded-xl p-4" style={{ background: "#ffb02008", border: "1px solid #ffb02022" }}>
          <p className="text-[12px] font-bold" style={{ color: "#ffb020" }}>💡 가장 중요한 규칙 하나만 기억한다면</p>
          <p className="text-[13px] font-bold text-white mt-1">보유 이유가 사라졌는지 정기적으로 점검하고, 그렇다면 매도한다</p>
          <p className="text-[12px] mt-1" style={{ color: "var(--text-muted)" }}>
            Undercurrent Sonar는 1~3년 펀더멘털 보유를 기본 전제로 합니다 — 단기 가격 변동에 따른 자동 손절은 없고,
            매수·매도 실행이나 보유 종목 추적 기능도 제공하지 않습니다. 재무 건전성 필터를 통과한 후보를
            정기적으로 다시 훑어보고, 애초에 보유 이유였던 스토리·촉매가 사라졌는지 본인이 직접 점검하세요.
          </p>
        </div>
      </Card>

      {/* 데이터 업데이트 */}
      <Card>
        <SectionTitle>데이터 업데이트 방식</SectionTitle>
        <div className="space-y-2 mb-4">
          {[
            { label: "워치리스트 스크리닝 (주 1회)", color: "#6fb3b8", desc: "매주 일요일 밤 자동 실행 — 재무 건전성 필터(트랩 필터) 통과 종목 전부를 순위 없이 리스트업하고, 곧바로 밸류(PSR/PER)·성장(매출 CAGR) 지표까지 계산", tag: "자동" },
            { label: "네러티브 브리프 (주 1회)", color: "#f87171", desc: "워치리스트 스크리닝 직후 후보·내 워치리스트 종목별 최근 1주 뉴스를 수집해 GPT가 장기 스토리·촉매·리스크·시장 단기 관심도(HOT/WARM/COLD)를 생성", tag: "자동" },
            { label: "시장 분석 (주 1회)", color: "#ffb020", desc: "매주 월요일 자동 실행 — 섹터 분석 갱신(한국은 KRX 코스피200 섹터지수, 미국은 SPDR ETF)", tag: "자동" },
            { label: "테마 레이더 (주 1회)", color: "#a78bfa", desc: "뉴스 수집 → 실적·주가 대조 → 6개 라벨 판정까지 매주 자동 갱신", tag: "자동" },
            { label: "분기 리서치 (분기 1회)", color: "#facc15", desc: "실제 분기 재무 발표(미국 10-Q, 한국 분기보고서) 시점마다 DART·yfinance에서 재수집해 4칸 분류를 다시 계산 — 주간 화면들과 달리 갱신 주기가 분기 단위입니다", tag: "분기 자동" },
            { label: "매일 밤 수집 (자동)", color: "#4ade80", desc: "한국 공시(공급계약·해지·잠정실적), 내부자 장내 매수(미국 S&P 500·400, 한국 시총 3000억+), 미국 8-K, 테마 이벤트 계산, 매크로·국고채·수급. GitHub 예약 실행이라 몇 시간 늦게 돌 수 있음", tag: "자동" },
            { label: "신호 기록·사후 확인 (주 1회)", color: "#a78bfa", desc: "일요일 밤 그 주 신호(내부자 매수·실적 반전·큰 공급계약·8-K·관심도 상승·테마 공시)를 적고, 4·12주 지난 신호의 결과를 채움 → 성적표", tag: "자동" },
            { label: "텔레그램 요약 (자동)", color: "#6fb3b8", desc: "주간 브리핑 요약을 폰으로 발송 - 맨 위 관심 종목에 생긴 일, 한국 공시·8-K·내부자 매수 포함. 정기 수집이 실패하면 실패 알림도", tag: "자동" },
            { label: "정성 체크리스트", color: "#a39c88", desc: "종목별 체크리스트·메모는 내가 직접 입력", tag: "수동" },
          ].map(({ label, color, desc, tag }) => (
            <div key={label} className="flex items-start gap-3 rounded-xl p-3" style={{ background: "var(--bg-inset)", border: `1px solid ${color}33` }}>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-[12px] font-bold" style={{ color }}>{label}</span>
                  <Badge text={tag} color={color} />
                </div>
                <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>{desc}</p>
              </div>
            </div>
          ))}
        </div>

        <SectionTitle>데이터 신선도 확인</SectionTitle>
        <div className="space-y-1">
          {[
            "사이드바 맨 아래 칸 — \"데이터 20개 모두 정상\"이면 끝. \"지연\"·\"없음\"이 보이면 눌러서 데이터 상태 화면에서 어느 칸인지 확인",
            "지연은 그 칸의 화면 숫자가 오래됐다는 뜻 — 해당 GitHub Actions 작업의 실행 결과를 확인하세요(실패면 텔레그램 알림도 옴)",
            "화면마다 제목 옆 \"○○ 기준 · 갱신 주기\" 표시 - 늦으면 노란 \"지연\"",
            "워치리스트 재스크리닝: GitHub → Actions → Weekly Watchlist Screen → Run workflow",
          ].map((step, i) => (
            <div key={i} className="flex items-start gap-3 py-1.5" style={{ borderBottom: "1px solid #262112" }}>
              <span className="text-[12px] font-black w-4 text-center shrink-0 mt-0.5" style={{ color: "#ffb020" }}>{i + 1}</span>
              <p className="text-[12px]" style={{ color: "var(--text-secondary)" }}>{step}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* What this tool does */}
      <Card>
        <SectionTitle>이 툴이 하는 것</SectionTitle>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {[
            ["워치리스트",      "재무 건전성 필터(Piotroski·ROE·부채비율·이자보상배율·현금흐름)를 통과한 종목을 주 1회, 순위 없이 리스트업. 여기에 밸류(PSR/PER, 같은 시장 후보 중 싼 편/중간/비싼 편)와 성장(매출 3년 CAGR, 성장/정체/역성장) 축을 더해 보여줌. 티커·종목명 검색 지원"],
            ["네러티브 브리프",  "후보 종목별 최근 뉴스를 GPT가 요약 — 장기 투자 스토리·촉매·리스크·시장 단기 관심도(HOT/WARM/COLD)"],
            ["섹터 분석",       "전환 중인 섹터 + 섹터별 지수 대비 상대강도. 한국은 코스피200 공식 섹터지수, 미국은 SPDR 11개 ETF 기준"],
            ["테마 레이더",     "미국·한국 산업 테마를 뉴스·실적·주가 세 축으로 주 1회 관찰, 정해진 조합에만 라벨 부여. Quiet(펀더멘털이 먼저)·Buzz(뉴스가 먼저)·Full(삼박자 동반) 3단계로 묶어서 표시"],
            ["분기 리서치",     "테마 소속 기업들의 분기 재무 신호(매출 전환·매출 흐름·이익 전환)와 뉴스 비율을 따로 봐서, 재무는 움직였는데 뉴스는 조용한 \"조용한 변화\" 테마를 찾아줌. 회사별 PSR/PER까지 표시"],
            ["텔레그램 알림",   "주간 분석 후 워치리스트 교차 히트·관심도 상승 신호를 요약해 폰으로 발송"],
            ["성적표",          "과거 후보에 실제 주가를 대조한 사후 검증 — 지수 단순 보유 대비 필터가 값을 더했는지. 신호 사후 확인으로 브리핑 칸마다 쓸모를 같은 잣대로"],
            ["공시·내부자 매수",  "한국 공시(공급계약·해지·잠정실적), 미국 8-K(항목 번호로 종류 + 원문 첫머리), 임원·대주주 장내 매수 - 브리핑·워치리스트 상세·테마 레이더(📄)에 원문 값 그대로"],
            ["정성 체크리스트", "워치리스트 팝업에 내장된 종목별 스토리·촉매 체크 + 메모"],
          ].map(([title, desc]) => (
            <div key={title} className="rounded-xl p-3" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
              <p className="text-[12px] font-semibold text-white mb-0.5">{title}</p>
              <p className="text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{desc}</p>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[12px] leading-relaxed" style={{ color: "var(--text-faint)" }}>
          ※ 실제 매매 주문·자동 거래는 지원하지 않습니다. 모든 예측은 확률적 참고 자료이며 수익을 보장하지 않습니다.
        </p>
      </Card>

      {/* Weekly routine */}
      <Card>
        <SectionTitle>주간 투자 의사결정 루틴</SectionTitle>
        <div className="space-y-2 mb-4">
          {[
            { n: "①", tab: "주간 브리핑 맨 위", action: "⭐ 관심 종목에 생긴 일 확인 - 내 관심·노트 종목의 실적 발표·공시·내부자 매수·실적 반전. 별일 없으면 이번 주 점검은 여기까지", href: "/briefing" },
            { n: "②", tab: "섹터 분석",     action: "전환 중인 섹터가 새로 생겼는지, 선행 섹터가 바뀌었는지 훑어보기", href: "/sector" },
            { n: "③", tab: "테마 레이더",   action: "라벨 붙은 테마가 있으면 훑어보기 — 특히 \"Quiet Strength\"는 뉴스만 봐서는 못 찾는 신호", href: "/radar" },
            { n: "④", tab: "분기 리서치",   action: "관심 가는 테마가 \"조용한 변화\"에 있는지, 소속 기업 재무 신호가 실제로 통과했는지 확인", href: "/quarterly" },
            { n: "⑤", tab: "워치리스트",    action: "밸류·성장·테마 필터로 후보를 좁힌 뒤 → 종목 클릭해 네러티브 브리프 읽기 + 공시·8-K·내부자 매수 + 정성 체크 + 메모", href: "/watchlist" },
            { n: "⑥", tab: "새 이름(선택)",  action: "브리핑 🆕 관심 밖 내부자 매수 - 눌러서 트랩 필터 판정·탈락 사유 확인. 재무가 받쳐주면 관찰 노트로", href: "/briefing#insider" },
            { n: "월", tab: "성적표 · 데이터 상태", action: "한 달에 한 번 신호 사후 확인(유니버스 대비)으로 어떤 칸이 쓸모 있는지, 데이터 상태로 끊긴 수집이 없는지", href: "/scorecard" },
          ].map(({ n, tab, action, href }) => (
            <div key={n} className="flex items-start gap-3 rounded-xl p-3" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
              <span className="text-sm font-black shrink-0 w-5 text-center" style={{ color: "#ffb020" }}>{n}</span>
              <div className="flex-1 min-w-0">
                <Link href={href} className="text-[12px] font-semibold text-white hover:underline">{tab}</Link>
                <p className="text-[12px] mt-0.5" style={{ color: "var(--text-muted)" }}>{action}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Trap filter thresholds */}
      <Card>
        <SectionTitle>재무 건전성 필터(트랩 필터) 구조</SectionTitle>
        <p className="text-[12px] mb-3 leading-relaxed" style={{ color: "var(--text-muted)" }}>
          점수를 매겨 순위를 매기는 게 아니라, 아래 항목 중 하나라도 걸리면 <span className="text-white font-semibold">탈락</span>하는
          방식입니다. 통과한 종목은 전부 워치리스트 후보가 되고(순위 없음), 그 안에서 어떤 종목을 살지는 본인이 판단합니다.
        </p>
        <div className="space-y-1">
          {[
            ["Piotroski F-Score", "6점 미만이면 탈락 (9개 항목 중 수익성·레버리지·운영효율 채점)"],
            ["이자보상배율(EBIT/이자비용)", "3배 미만이면 탈락 — 이자는 내지만 안전마진이 부족한 상태도 제외"],
            ["부채비율(총부채/자기자본)", "150% 초과면 탈락 (금융업 제외)"],
            ["영업현금흐름", "최근 2년 연속 마이너스면 탈락"],
            ["매출 + 순이익", "3년 연속 동시 감소면 탈락 (매출만 2년 연속 감소도 별도 감점 사유)"],
            ["ROE", "미국 12% · 한국 8% 미만이면 탈락 (시장별 기준)"],
          ].map(([f, tip]) => (
            <div key={f} className="flex flex-col gap-0.5 py-1.5 text-[12px] sm:flex-row sm:items-center sm:gap-2" style={{ borderBottom: "1px solid #262112" }}>
              <span className="font-semibold sm:w-48 sm:shrink-0" style={{ color: "var(--text-secondary)" }}>{f}</span>
              <span className="flex-1" style={{ color: "#726b58" }}>{tip}</span>
            </div>
          ))}
        </div>
        <div className="rounded-xl p-3 mt-4" style={{ background: "#0e0d08", border: "1px solid #262112" }}>
          <p className="text-[12px] font-bold mb-1.5" style={{ color: "#facc15" }}>왜 모멘텀·기술적 지표는 안 보나?</p>
          <p className="text-[12px] leading-relaxed" style={{ color: "#a39c88" }}>
            예전 버전은 기술적 지표·상대강도·거래량으로 &quot;지금 살 타이밍인가&quot;까지 점수화했고, 한때는
            시장 체제·마켓 게이트로 진입 타이밍까지 판정했습니다. 1~3년 보유를 전제로 하면 그 시점의 단기
            타이밍은 큰 의미가 없다고 판단해 모두 제거했습니다. 지금은 재무가 건전한 회사인지만 걸러내고,
            언제·얼마나 살지는 전적으로 본인이 판단합니다.
          </p>
        </div>
      </Card>

      {/* AI 신뢰도 + 워크플로우 종목 우선순위 */}
      <Card>
        <SectionTitle>알아두면 유용한 해석법</SectionTitle>
        <div className="space-y-3">

          {/* 밸류 vs 성장 */}
          <div>
            <p className="text-[12px] font-bold text-white mb-1">워치리스트의 &quot;밸류&quot;와 &quot;성장&quot;은 기준이 다릅니다</p>
            <p className="text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
              둘 다 3단계 등급이지만 나누는 방식이 다릅니다. <span className="text-white">밸류(싼 편/중간/비싼 편)</span>는
              지금 화면에 뜬 후보들을 PSR 기준으로 순서대로 줄 세워 3등분한 <span className="text-white">상대 등급</span>입니다 —
              절대적으로 싸다는 뜻이 아니라 &quot;이 후보들 중에서&quot; 싼 쪽이라는 뜻입니다.
              <span className="text-white"> 성장(성장/정체/역성장)</span>은 반대로 매출 3년 성장률이 0%·10%를 넘는지 보는
              <span className="text-white"> 절대 기준</span>입니다 — 후보 대부분이 이미 성장 중이라 상대 등급으로 나누면
              실제로 성장 중인 기업에도 &quot;역성장&quot; 라벨이 붙어버리기 때문입니다.
            </p>
            <p className="text-[12px] mt-1.5" style={{ color: "#726b58" }}>
              ※ 두 등급을 곱하거나 더해서 하나의 점수로 만들지 않습니다 — &quot;싼 편&quot;이면서 &quot;역성장&quot;인 종목은
              재무는 건전한데 매출이 줄면서 시장이 싸게 평가해 둔 <span className="text-white">가치 함정</span>일 수 있다는
              신호이지, 무시해도 되는 오류가 아닙니다. 반대로 &quot;성장&quot;이면서 &quot;비싼 편&quot;이면 이미 기대가 반영된
              값이라는 뜻입니다.
            </p>
          </div>

          <div style={{ borderTop: "1px solid #262112", paddingTop: "1rem" }}>
            <p className="text-[12px] font-bold text-white mb-1">분기 리서치와 워치리스트의 PSR 등급이 다르게 나오는 건 오류가 아닙니다</p>
            <p className="text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
              같은 종목의 PSR 수치 자체는 두 화면이 동일한 계산식을 씁니다. 다만 등급을 매기는
              <span className="text-white"> 비교 대상이 다릅니다</span> — 분기 리서치는 같은 테마 소속 기업들 안에서,
              워치리스트는 같은 시장의 후보 전체 안에서 3등분합니다. 비교 집단이 다르니 등급도 다르게 나오는 게 맞습니다.
            </p>
          </div>

          {/* 시장 단기 관심도 */}
          <div style={{ borderTop: "1px solid #262112", paddingTop: "1rem" }}>
            <p className="text-[12px] font-bold text-white mb-1">네러티브 브리프의 &quot;시장 단기 관심도&quot;란?</p>
            <p className="text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
              최근 1주일 뉴스량을 기준으로 GPT가 매기는 HOT/WARM/COLD 표시입니다.
              <span className="text-white"> 장기 투자 판단의 핵심 지표가 아니라 보조 정보</span>일 뿐입니다 —
              관심 밖(COLD)이어도 장기 스토리(story)는 탄탄할 수 있고, 반대로 HOT이라고 재무가 좋은 것도 아닙니다.
            </p>
            <div className="flex gap-2 mt-2">
              {[
                { range: "🔥 HOT", desc: "뉴스 많음, 인기 테마", color: "#f87171" },
                { range: "🌤 WARM", desc: "꾸준한 관심", color: "#facc15" },
                { range: "❄️ COLD", desc: "뉴스 적음, 관심 밖", color: "#6fb3b8" },
              ].map(({ range, desc, color }) => (
                <div key={range} className="flex-1 rounded-lg px-2.5 py-2 text-center" style={{ background: `${color}10`, border: `1px solid ${color}30` }}>
                  <p className="text-[12px] font-black" style={{ color }}>{range}</p>
                  <p className="text-[12px] mt-0.5" style={{ color: "#726b58" }}>{desc}</p>
                </div>
              ))}
            </div>
            <p className="text-[12px] mt-1.5" style={{ color: "#726b58" }}>※ 판단의 중심은 항상 story(투자 스토리)·catalysts(촉매)·risks(리스크)입니다.</p>
          </div>

          <div style={{ borderTop: "1px solid #262112", paddingTop: "1rem" }}>
            <p className="text-[12px] font-bold text-white mb-1">워치리스트 후보에는 왜 순위가 없나?</p>
            <p className="text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
              예전 버전은 재무 필터 통과 종목을 다시 모멘텀·품질 점수로 줄 세워 상위 50개만 보여줬습니다.
              하지만 1~3년 보유가 전제라면 스크리닝 시점의 순위가 실제 투자 성과와 크게 상관없다고 판단해 랭킹 자체를 없앴습니다.
              지금은 재무 필터를 통과한 종목 <span className="text-white">전부</span>가 후보이고, 그 안에서 무엇을 살지는
              밸류·성장·섹터 분산·네러티브·본인의 확신을 기준으로 직접 고르는 게 맞는 방향이라고 봤습니다.
            </p>
          </div>

        </div>
      </Card>

      {/* Tab reference */}
      <Card>
        <SectionTitle>전체 탭 한눈에 보기</SectionTitle>
        <div className="space-y-1">
          {GUIDE_SECTIONS.map((t) => (
            <div key={t.href} className="flex items-start gap-3 py-2" style={{ borderBottom: "1px solid #262112" }}>
              <span className="w-4 text-center text-base shrink-0" style={{ color: "#ffb020" }}>{t.icon}</span>
              <Link href={t.href} className="text-[12px] font-semibold text-white hover:underline w-28 shrink-0">{t.label}</Link>
              <p className="text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{t.desc}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* FAQ */}
      <Card>
        <SectionTitle>자주 묻는 질문</SectionTitle>
        <div className="space-y-3">
          {[
            {
              q: "워치리스트의 밸류·성장 지표가 '-'로 떠요.",
              a: "PSR은 최근 4분기 매출을, 성장은 최근 4개 회계연도 매출을 정확히 연속·간격대로 구해야 계산됩니다. 신규 상장이라 재무 이력이 짧거나 공시 공백이 있으면 계산하지 않고 '-'로 남깁니다 — 이는 계산 오류가 아니라 데이터부족이며, '탈락'과는 다른 상태입니다.",
            },
            {
              q: "네러티브 브리프가 없는 종목이 있어요.",
              a: "내 워치리스트 종목과 이번 주 후보는 모두 대상이지만, 후보 수가 많으면 오래된(또는 아직 없는) 종목부터 순서대로 매주 나눠서 갱신됩니다(회차당 최대 400종목). 며칠~몇 주 걸릴 수 있으니 조금 기다리거나 GitHub → Actions에서 Weekly Watchlist Screen을 수동 실행하세요.",
            },
            {
              q: "워치리스트 후보는 어떻게 뽑히나요?",
              a: "주 1회 자동 스크리닝 — 함정 필터(Piotroski≥6, ROE≥12%(한국 8%), 이자보상배율≥3, 부채비율≤150%, 영업현금흐름 2년 연속 마이너스 아님, 매출+순이익 3년 연속 감소 아님)를 통과한 종목 전부가 후보입니다. 더 이상 점수로 순위를 매겨 상위 N개만 자르지 않습니다. 스크리닝 직후 밸류(PSR/PER)와 성장(매출 CAGR) 지표도 같이 계산됩니다.",
            },
            {
              q: "분기 리서치 화면에 '데이터부족'이 유독 많이 보여요.",
              a: "분기 재무는 분기 1회만 갱신됩니다. 미국 10-Q, 한국 분기보고서가 실제로 공시되는 시점(대략 분기 말 후 4~6주)에만 그 분기 데이터가 들어오므로, 공시 발표 직후에는 최신 분기 판정이 아직 없어 데이터부족이 많이 보일 수 있습니다 — 다음 분기 재무가 들어오면 자동으로 갱신됩니다.",
            },
            {
              q: "테마 레이더의 📄 공시·내부자 매수 표시는 무엇인가요?",
              a: "테마 소속 기업(직접·부분 연관)에 최근 7일 나온 공시와 내부자 장내 매수를 센 것입니다. 한국은 DART 공급계약·계약 해지·계약금액 정정·잠정실적, 미국은 SEC 8-K(실적 발표만 있는 것 제외), 두 시장 모두 임원·대주주의 장내 매수. 세 축 화살표·라벨에는 들어가지 않습니다(점수 아님). 옆의 \"평소\"는 그 테마의 직전 4주 주당 평균이고, 평소의 2배 이상(공시 3건·내부자 2개사 이상)이면 굵게 표시합니다 - 한국처럼 공급계약 공시가 원래 흔한 테마가 늘 많아 보이지 않게, 테마끼리가 아니라 자기 평소와 비교합니다. 데이터가 2주 미만이면 비교하지 않습니다. 펼치면 주별 숫자·최근 30일 목록·원문 링크가 있고, 세 축이 다 조용한데 공시가 평소보다 많은 테마는 아래 \"축은 조용, 소속 기업 공시는 평소보다 많음\"에 따로 모입니다. 매일 밤(14:00 UTC) 갱신.",
            },
            {
              q: "성적표의 \"신호 사후 확인\"은 어떻게 읽나요?",
              a: "신호가 나온 주 월요일 이후 첫 거래일부터 4주·12주 뒤 수익률에서 비교 기준의 같은 기간 수익률을 뺀 값(초과수익)의 중앙값과 사분위(가운데 절반이 놓인 범위)입니다. 기본 비교 기준은 같은 유니버스 전체 종목의 중앙값 - 신호 종목은 대부분 중소형주라 대형주 비중이 큰 지수와만 비교하면 그 기간 중소형주가 강했는지가 섞입니다. \"기대: 하락\" 표시(해지·8-K 주의)는 마이너스면 신호가 맞은 쪽. 표본이 적은 동안(몇 달)은 결론을 내리지 말고 방향만 보세요. \"소급\"은 기록 시작 전 주를 나중에 다시 만든 것입니다.",
            },
            {
              q: "브리핑 🆕 관심 밖 새 이름의 \"재무 미확인\"은 무슨 뜻인가요?",
              a: "내부자 매수가 나온 종목이 이번 주 트랩 필터 스크리닝 결과에 없다는 뜻입니다(유니버스 밖이거나 아직 안 돌았음). 탈락이 아닙니다. 통과·탈락·데이터부족이 붙은 종목은 눌러서 탈락 사유까지 볼 수 있습니다.",
            },
            {
              q: "테마 레이더의 발견 단계(Quiet/Buzz/Full) 섹션이 접혀 있어요.",
              a: "기본적으로 접힌 채로 시작합니다 — 세 단계 모두 해당 테마가 없는 주에는 빈 안내만 세 번 반복돼 화면을 다 차지하는 문제가 있었습니다. 제목을 클릭하면 펼쳐지고, 한 번 펼친 상태는 다음 방문 때도 브라우저에 기억됩니다.",
            },
            {
              q: "섹터 분석에 'KRX 공식 지수' 또는 '대표 종목 기준 (폴백)' 배지가 떠요.",
              a: "한국 섹터 분석은 KRX가 직접 산출하는 코스피200 섹터지수를 우선 씁니다. 지수를 받아오지 못하면(일시적 장애 등) 대표 종목 몇 개의 평균으로 대체 계산하고 그 사실을 배지로 알려줍니다 — 두 경우 다 계산 자체는 정상입니다.",
            },
            {
              q: "부채비율·이자보상배율이 숫자 대신 '무차입'·'자본잠식'으로 떠요.",
              a: "숫자가 없는 게 아니라 그 자체가 의미 있는 상태입니다. '무차입'은 이자비용이 없어 계산이 불필요한 좋은 상태, '자본잠식(음수 자본)'은 자기자본이 마이너스라 원인을 직접 확인해야 하는 주의 상태입니다. '데이터 없음'만 진짜 결측치입니다.",
            },
            {
              q: "재무 필터를 통과했는데도 손실이 날 수 있나요?",
              a: "네. 필터는 재무가 명백히 부실한 종목을 걸러낼 뿐 매수·매도 신호가 아닙니다. 통과 종목이라도 주가가 하락할 수 있고, 이 도구는 손절선·포지션 크기를 계산해주지 않습니다.",
            },
            {
              q: "데이터가 없거나 '—' 표시가 뜨는 경우는?",
              a: "분석 파이프라인이 실행되지 않았거나 API 오류입니다. 해당 분석 스크립트를 실행하고 F5로 새로고침하세요.",
            },
          ].map(({ q, a }) => (
            <div key={q}>
              <p className="text-[12px] font-semibold text-white mb-1">Q. {q}</p>
              <p className="text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{a}</p>
            </div>
          ))}
        </div>
      </Card>

      <p className="text-[12px] text-center pb-4" style={{ color: "#423e33" }}>
        Undercurrent Sonar는 투자 참고 도구입니다. 최종 투자 판단과 책임은 항상 본인에게 있습니다.
      </p>
    </div>
  );
}
