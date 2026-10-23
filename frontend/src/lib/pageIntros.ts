// 화면마다 맨 위 "이 화면은?" 상자 문구(2026-10-23, 처음 쓰는 사람 안내).
// 세 줄 형식을 지킨다: 무엇을 보여주나 / 언제 보나 / 여기서 할 일. terms는 상자 아래 "이 화면의 용어"로
// 뜨는 용어 사전 키(src/lib/glossary.ts). 매수 추천처럼 읽히는 말은 쓰지 않는다.
import type { GlossaryKey } from "@/src/lib/glossary";

export type PageIntro = {
  what: string;
  when: string;
  todo: string;
  terms?: GlossaryKey[];
};

export const PAGE_INTROS = {
  home: {
    what: "이번 주에 새로 생긴 일(새 후보, 실적 발표, 공시, 내부자 매수)과 금리·환율 같은 시장 날씨를 한 화면에 모았습니다.",
    when: "월요일 아침, 가장 먼저.",
    todo: "숫자가 있는 칸을 누르면 그 목록으로 갑니다. 아래 그래프는 판정 없이 사실만 보여줍니다.",
    terms: ["turnaround", "insider_buy", "disclosure", "macro"],
  },
  briefing: {
    what: "지난 한 주 동안 내 관심 종목과 테마에 생긴 일을 정리한 주간 문서입니다. 텔레그램으로도 옵니다.",
    when: "월요일 아침, 개요 다음.",
    todo: "맨 위 ⭐ 관심 종목 칸부터 보세요. 공시·실적 발표·내부자 매수 중 내 종목 소식이 있는지 확인합니다.",
    terms: ["disclosure", "insider_buy", "earnings_surprise", "turnaround"],
  },
  radar: {
    what: "산업 테마 30여 개를 뉴스·실적·주가 세 가지로 매주 관찰합니다. 정해진 조합에만 이름(라벨)을 붙이고 나머지는 화살표만 둡니다.",
    when: "월요일, 브리핑 다음.",
    todo: "라벨이 붙은 테마, 특히 실적이 먼저 움직인 '조용한 강세'부터 봅니다. 테마를 펼치면 소속 기업과 근거가 나옵니다.",
    terms: ["theme", "axis", "arrow", "quiet_strength", "member"],
  },
  radar_theme: {
    what: "테마 하나의 최근 12주 흐름과, 그 흐름을 만든 소속 기업들입니다.",
    when: "레이더에서 눈에 띈 테마를 더 알고 싶을 때.",
    todo: "세 축 중 무엇이 먼저 움직였는지 보고, 아래 기업 표에서 실적이 좋아진 회사를 찾습니다.",
    terms: ["axis", "arrow", "member", "earnings_surprise"],
  },
  sector: {
    what: "업종별로 주가가 시장보다 강한지 약한지(상대강도)를 보여줍니다.",
    when: "가끔. 시장 분위기를 감 잡고 싶을 때.",
    todo: "강해지는 업종과 약해지는 업종을 보고, 관심 테마가 속한 업종의 흐름을 확인합니다.",
    terms: ["rs"],
  },
  quarterly: {
    what: "분기 실적이 나오면 테마를 재무 신호와 뉴스 비율로 4칸에 나눕니다.",
    when: "실적 시즌(분기에 한 번, 실적 발표 4-6주 뒤).",
    todo: "'조용한 변화' 칸(재무는 바뀌었는데 뉴스는 조용한 테마)을 먼저 봅니다.",
    terms: ["quarterly_class", "theme"],
  },
  watchlist: {
    what: "재무가 튼튼한 종목만 거른 목록입니다. 순위는 없고, 매수 추천도 아닙니다.",
    when: "관심 테마가 생긴 뒤.",
    todo: "'테마 흐름과 겹치는 종목'이나 싼 편·성장 필터로 좁혀 보고, 종목을 눌러 재무·공시·스토리를 확인합니다. 마음에 들면 '내 워치리스트'에 담고 메모를 남깁니다.",
    terms: ["trap_filter", "no_rank", "psr", "growth", "fscore"],
  },
  notes: {
    what: "테마나 종목에 대한 내 예상을 적어두면, 4주·12주 뒤 그때 값과 지금 값을 나란히 보여줍니다.",
    when: "예상이 생겼을 때 적고, 회고가 도착하면(브리핑에 알림) 판정합니다.",
    todo: "맞았는지 직접 판정하고 배운 점을 한 줄 남깁니다. 적은 예상은 고칠 수 없습니다 - 나중에 기억을 바꾸지 않기 위해서입니다.",
    terms: ["axis"],
  },
  scorecard: {
    what: "이 툴이 과거에 고른 후보들이 실제로 잘 됐는지 사후에 확인합니다.",
    when: "몇 달에 한 번.",
    todo: "툴을 얼마나 믿을지 판단하는 데 씁니다. 180일 이상 결과와 표본 수를 함께 보세요 - 짧은 기간 숫자는 우연이 큽니다.",
    terms: ["trap_filter", "insider_buy"],
  },
} satisfies Record<string, PageIntro>;

export type PageIntroKey = keyof typeof PAGE_INTROS;

// localStorage 키 - 가이드의 "안내 다시 보기"가 이 접두어로 전부 지운다.
export const INTRO_STORAGE_PREFIX = "usonar_intro_closed:";
export const WELCOME_STORAGE_KEY = "usonar_welcome_closed";
