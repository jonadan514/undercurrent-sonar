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
    what: "미국·한국 두 시장에 이번 주 새로 생긴 일(새 후보, 실적 발표, 공시, 내부자 매수)을 단락으로 나란히, 금리·환율 같은 시장 날씨는 공통으로 한 화면에 모았습니다.",
    when: "월요일 아침, 가장 먼저.",
    todo: "숫자를 누르면 해당 목록으로 갑니다. 아래 그래프는 판정 없이 사실만 보여줍니다.",
    terms: ["turnaround", "insider_buy", "disclosure", "macro"],
  },
  briefing: {
    what: "지난 한 주 동안 내 관심 종목과 테마에 생긴 일을 정리한 주간 문서입니다. 텔레그램으로도 옵니다.",
    when: "월요일 아침, 개요 다음.",
    todo: "맨 위 ⭐ 관심 종목부터 보세요. 공시·실적 발표·내부자 매수 중 내 종목 소식이 있는지 확인합니다.",
    terms: ["disclosure", "insider_buy", "earnings_surprise", "turnaround"],
  },
  radar: {
    what: "산업 테마 30여 개를 뉴스·실적·주가 세 가지로 매주 관찰합니다. 정해진 조합에만 이름(라벨)을 붙이고 나머지는 화살표만 둡니다.",
    when: "월요일, 브리핑 다음.",
    todo: "라벨이 붙은 테마, 특히 실적이 먼저 움직인 '숨은 강세'부터 봅니다. 테마를 펼치면 소속 기업과 근거가 나옵니다.",
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
    todo: "'Hidden · 숨은 개선'(재무는 좋아졌는데 뉴스는 조용한 테마)부터 봅니다.",
    terms: ["quarterly_class", "theme"],
  },
  watchlist: {
    what: "재무가 튼튼한 종목만 거른 목록입니다. 순위는 없고, 매수 추천도 아닙니다.",
    when: "관심 테마가 생긴 뒤.",
    todo: "'테마 흐름과 겹치는 종목'이나 밸류 LOW·성장 필터로 좁혀 보고, 종목을 눌러 재무·공시·스토리를 확인합니다. 마음에 들면 '내 워치리스트'에 담고 메모를 남깁니다.",
    terms: ["trap_filter", "no_rank", "psr", "growth", "fscore"],
  },
  notes: {
    what: "테마나 종목에 대한 내 예상을 적어두면, 4주·12주 뒤 그때 값과 지금 값을 나란히 보여줍니다.",
    when: "예상이 생겼을 때 적고, 회고가 도착하면(브리핑에 알림) 판정합니다.",
    todo: "맞았는지 직접 판정하고 배운 점을 한 줄 남깁니다. 적은 예상은 고칠 수 없습니다 - 나중에 기억을 바꾸지 않기 위해서입니다.",
    terms: ["axis"],
  },
  scorecard: {
    what: "이 도구가 과거에 고른 후보들이 실제로 잘 됐는지 사후에 확인합니다.",
    when: "몇 달에 한 번.",
    todo: "도구를 얼마나 믿을지 판단하는 데 씁니다. 180일 이상 결과와 표본 수를 함께 보세요 - 짧은 기간 숫자는 우연이 큽니다.",
    terms: ["trap_filter", "insider_buy"],
  },
  investors: {
    what: "버크셔·바우포스트·드러켄밀러 등 직접 고른 운용사 15곳이 분기 말에 무엇을 새로 사고, 늘리고, 다 팔았는지(13F) 보여줍니다.",
    when: "분기마다 - 13F는 분기 끝나고 45일 안에 나옵니다(2월·5월·8월·11월 중순).",
    todo: "여러 곳이 함께 산 종목이나 내 테마에 걸리는 새 종목을 눌러 재무 판정·테마 동료 비교를 보고, 이유가 궁금하면 관찰 노트로. 매수 신호가 아니라 45일 늦은 사실입니다.",
    terms: ["form_13f", "trap_filter"],
  },
  report: {
    what: "지난 한 달을 한 장으로 묶은 보고서입니다 - 시장 환경, 라벨이 붙은 테마, 주요 기사, 테마별 기업 지도, 워치리스트 변화, 관찰 노트 회고, 다음 달 일정. 매달 첫 월요일 아침에 지난달 것이 만들어집니다.",
    when: "매달 첫 월요일. 주간 브리핑으로 놓친 흐름을 한 번에 훑을 때.",
    todo: "맨 위 요약으로 흐름을 잡고, 기업 지도에서 이름을 눌러 기업 카드로 들어갑니다. 요약은 아래 칸의 사실만으로 GPT가 쓴 글이라 숫자·전망은 없고, 숫자는 각 칸에 원래 값 그대로 있습니다. '인쇄 · PDF로 저장'으로 종이로도 볼 수 있습니다.",
    terms: ["theme", "axis", "quiet_strength", "trap_filter"],
  },
  calendar: {
    what: "실적 발표, 13F·분기보고서 마감, 관찰 노트 회고가 오는 날, 브리핑·월간 보고서가 나오는 날을 한 달 달력에 모았습니다.",
    when: "주초에 이번 주·다음 주를, 실적 시즌에는 수시로.",
    todo: "내 관심(앰버)·관찰 노트(청록) 종목부터 봅니다. 위 칩으로 후보·테마 소속·시장을 거르고, 이름을 누르면 기업 카드로 갑니다. 물음표(?) 날짜는 회사가 아직 확정하지 않아 바뀔 수 있습니다.",
    terms: ["earnings_surprise", "form_13f"],
  },
} satisfies Record<string, PageIntro>;

export type PageIntroKey = keyof typeof PAGE_INTROS;

// localStorage 키 - 가이드의 "안내 다시 보기"가 이 접두어로 전부 지운다.
export const INTRO_STORAGE_PREFIX = "usonar_intro_closed:";
export const WELCOME_STORAGE_KEY = "usonar_welcome_closed";
