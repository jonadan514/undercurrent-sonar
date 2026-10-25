"use client";

import { useState } from "react";
import GuideTabs from "@/src/components/GuideTabs";
import PageHeader from "@/src/components/PageHeader";

interface Section {
  id: string;
  icon: string;
  title: string;
  subtitle: string;
  content: React.ReactNode;
}

function Accordion({ sections }: { sections: Section[] }) {
  const [open, setOpen] = useState<string | null>(sections[0]?.id ?? null);
  return (
    <div className="space-y-2">
      {sections.map((s) => {
        const isOpen = open === s.id;
        return (
          <div key={s.id} className="bg-card rounded-xl overflow-hidden">
            <button
              className="w-full flex items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-white/[0.02]"
              onClick={() => setOpen(isOpen ? null : s.id)}
            >
              <span className="text-lg w-6 text-center shrink-0" style={{ color: "#ffb020" }}>{s.icon}</span>
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-semibold text-white">{s.title}</p>
                <p className="text-[12px] mt-0.5" style={{ color: "var(--text-muted)" }}>{s.subtitle}</p>
              </div>
              <span className="text-[13px] shrink-0 transition-transform duration-200" style={{
                color: "#ffb020",
                transform: isOpen ? "rotate(180deg)" : "rotate(0deg)",
                display: "inline-block",
              }}>▼</span>
            </button>
            {isOpen && (
              <div className="px-5 pb-5 pt-1 border-t" style={{ borderColor: "var(--border)" }}>
                {s.content}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="text-[12px] leading-relaxed mb-2" style={{ color: "var(--text-secondary)" }}>{children}</p>;
}
function H({ children }: { children: React.ReactNode }) {
  return <p className="text-[12px] font-bold text-white mt-4 mb-1.5">{children}</p>;
}
function Note({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl px-4 py-3 mt-3 text-[12px] leading-relaxed" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
      {children}
    </div>
  );
}
function Table({ headers, rows }: { headers: string[]; rows: (string | React.ReactNode)[][] }) {
  return (
    <div className="rounded-xl overflow-x-auto mt-3" style={{ border: "1px solid var(--border)" }}>
      <table className="w-full text-[13px]">
        <thead>
          <tr style={{ background: "var(--bg-inset)", borderBottom: "1px solid var(--border)" }}>
            {headers.map((h) => (
              <th key={h} className="whitespace-nowrap px-3 py-2 text-left text-[12px] font-semibold" style={{ color: "var(--text-muted)" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ borderBottom: i < rows.length - 1 ? "1px solid var(--border-dim)" : "none" }}>
              {row.map((cell, j) => (
                <td key={j} className={`px-3 py-2.5 text-[12px] ${j === 0 ? "whitespace-nowrap" : ""}`} style={{ color: j === 0 ? "var(--text-primary)" : "var(--text-secondary)" }}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function Highlight({ children }: { children: React.ReactNode }) {
  return <span className="font-semibold" style={{ color: "#ffb020" }}>{children}</span>;
}
function Warn({ children }: { children: React.ReactNode }) {
  return <span className="font-semibold" style={{ color: "#facc15" }}>{children}</span>;
}
function Danger({ children }: { children: React.ReactNode }) {
  return <span className="font-semibold" style={{ color: "#f87171" }}>{children}</span>;
}

const SECTIONS: Section[] = [
  {
    id: "screening",
    icon: "★",
    title: "재무 건전성 필터 — Piotroski F-Score란",
    subtitle: "점수로 줄 세우지 않고, 걸리면 탈락하는 방식으로 바뀐 이유",
    content: (
      <>
        <P>
          예전 버전은 기술·펀더멘털·상대강도·거래량 등을 가중 합산해 <Highlight>0~100점짜리 복합 점수</Highlight>를
          만들고 시장별 상위 50개만 후보로 남겼습니다. 1~3년 보유가 전제인 지금은 그 방식을 걷어내고,
          <Highlight> 재무가 건전한지만 걸러내는 함정 필터</Highlight>로 단순화했습니다 — 통과하면 순위 없이 전부 후보가 됩니다.
        </P>
        <Note>
          💡 처음엔 "명백히 위험한 것만 제외"하는 느슨한 기준(Piotroski≥5, ROE≥8% 등)이었는데,
          570종목 중 302개(53%)가 통과해 실사용에 너무 많았습니다. "확실히 우량한 것만 통과"로
          기준을 올려 지금의 값이 됐습니다.
        </Note>
        <H>탈락 기준 (하나라도 걸리면 제외)</H>
        <Table
          headers={["항목", "탈락 기준"]}
          rows={[
            ["Piotroski F-Score", "6점 미만 (아래 9개 항목 중 6개 미만 충족)"],
            ["이자보상배율(EBIT/이자비용)", "3배 미만 — 이자는 내지만 안전마진이 부족한 상태도 제외"],
            ["부채비율(총부채/자기자본)", "150% 초과 (금융업 제외)"],
            ["영업현금흐름", "최근 2년 연속 마이너스"],
            ["매출 + 순이익", "3년 연속 동시 감소 (매출만 2년 연속 감소도 별도 감점 사유)"],
            ["ROE", "미국 12% / 한국 8% 미만 (시장별 기준)"],
          ]}
        />
        <H>Piotroski F-Score 9개 항목</H>
        <P>재무제표 3개년(손익·재무상태·현금흐름)을 비교해 각 항목을 충족하면 1점씩, 최대 9점을 매깁니다.</P>
        <Table
          headers={["구분", "항목", "충족 조건"]}
          rows={[
            ["수익성", "ROA 양수", "총자산순이익률(ROA) > 0"],
            ["수익성", "영업현금흐름 양수", "CFO > 0"],
            ["수익성", "ROA 개선", "전년 대비 ROA 증가"],
            ["수익성", "이익의 질", "영업현금흐름 > ROA (회계상 이익보다 실제 현금흐름이 더 좋음)"],
            ["재무구조", "레버리지 감소", "부채비율(장기부채/자산) 전년보다 하락"],
            ["재무구조", "유동성 개선", "유동비율 전년보다 상승"],
            ["재무구조", "희석 없음", "발행주식수가 전년보다 늘지 않음"],
            ["운영효율", "매출총이익률 개선", "전년보다 상승"],
            ["운영효율", "자산회전율 개선", "전년보다 상승"],
          ]}
        />
        <Note>
          💡 이 필터는 <Highlight>&quot;뭘 사라&quot;가 아니라 &quot;뭘 사지 마라&quot;를 걸러주는 수비 필터</Highlight>입니다.
          통과했다고 반드시 좋은 투자처라는 뜻은 아니며, 어떤 종목을 실제로 살지는 밸류·성장 지표와
          네러티브 브리프, 본인의 판단으로 결정하세요.
        </Note>
      </>
    ),
  },
  {
    id: "valuation-growth",
    icon: "$",
    title: "워치리스트의 밸류(PSR/PER)·성장(매출 CAGR) 지표",
    subtitle: "\"탄탄한데 싸기도 한가\", \"탄탄한데 자라기도 하는가\"를 보는 두 축",
    content: (
      <>
        <P>
          재무 건전성 필터를 통과한 종목이라도 전부 매력적인 건 아닙니다. 무차입 흑자 기업인데
          매출이 3년째 줄어드는 <Highlight>가치 함정</Highlight>도 필터는 그냥 통과시킵니다. 밸류·성장
          두 지표는 이 필터가 못 보는 부분을 보여주기 위해 추가됐습니다.
        </P>
        <H>밸류 (PSR / PER) — 상대 등급</H>
        <P>
          PSR = 시가총액 ÷ 최근 4분기 매출 합. PER = 시가총액 ÷ 최근 4분기 순이익 합(적자 기업은
          표시하지 않음). 이 수치 자체보다 중요한 건 <Highlight>등급을 나누는 방식</Highlight>입니다 —
          지금 화면에 뜬 후보들을 PSR이 낮은 순으로 줄 세워 정확히 3등분합니다.
        </P>
        <Table
          headers={["등급", "뜻"]}
          rows={[
            ["싼 편", "같은 시장 후보 중 PSR 하위 1/3"],
            ["중간", "가운데 1/3"],
            ["비싼 편", "상위 1/3"],
            ["-", "4분기 재무가 이어지지 않아 계산 불가 (데이터부족, 탈락 아님)"],
          ]}
        />
        <Note>
          💡 &quot;싼 편&quot;은 절대적으로 싸다는 뜻이 아니라 <Highlight>이 후보들 중에서</Highlight> 싼 쪽이라는
          뜻입니다. 순위나 점수가 아니라 위치를 보여주는 것뿐이라, &quot;비싼 편&quot;이라고 나쁜 종목인 것도 아닙니다.
        </Note>
        <H>성장 (매출 3년 CAGR·최근 1년) — 절대 기준</H>
        <P>
          연차 재무제표의 최근 4개 회계연도(정확히 3년 간격)로 매출 연평균성장률(CAGR)을 구합니다.
          밸류와 달리 <Highlight>절대 기준</Highlight>을 씁니다 — 실제로 재봤더니 후보의 86~93%가 이미
          양의 성장 중이라, 밸류처럼 순위로 3등분하면 +3% 성장 중인 멀쩡한 기업에도 &quot;역성장&quot;
          라벨이 붙어버렸기 때문입니다.
        </P>
        <Table
          headers={["등급", "기준"]}
          rows={[
            ["성장", "매출 3년 CAGR 10% 이상"],
            ["정체", "0% ~ 10%"],
            ["역성장", "0% 미만 — 매출이 3년간 줄었다는 사실 그 자체"],
            ["-", "회계기간이 부족하거나 연도 간격이 맞지 않아 계산 불가"],
          ]}
        />
        <Note>
          💡 &quot;역성장&quot;은 <Danger>재무 부실을 뜻하지 않습니다</Danger> — 무차입 흑자 기업도 얼마든지
          매출이 줄 수 있습니다. 배지 색도 F-Score 탈락 같은 위험 신호(빨강)와 구분해 주황으로 표시합니다.
        </Note>
        <H>두 지표를 같이 보면 보이는 것</H>
        <Table
          headers={["밸류", "성장", "해석"]}
          rows={[
            ["싼 편", "역성장", "재무는 건전한데 매출이 줄어 시장이 싸게 평가해 둔 상태 — 가치 함정일 수도, 저평가 기회일 수도 있습니다. 이유를 직접 확인할 가치가 있는 조합"],
            ["싼 편", "성장", "탄탄하고 싸고 자라는 종목 — 이 화면에서 가장 먼저 눈여겨볼 만한 조합"],
            ["비싼 편", "성장", "이미 시장이 성장을 알고 있어 값이 붙은 상태"],
          ]}
        />
        <Note>
          💡 두 지표를 곱하거나 더해서 하나의 점수로 만들지 않습니다. 워치리스트 화면의 &quot;싼 편만&quot;·
          &quot;성장만&quot; 필터 버튼을 각각 눌러 직접 조합해 보세요 — 조합을 만드는 건 항상 사용자입니다.
        </Note>
      </>
    ),
  },
  {
    id: "ai",
    icon: "◎",
    title: "네러티브 브리프 — GPT 요약 자세히 읽는 법",
    subtitle: "워치리스트 종목 클릭 시 뜨는 뉴스 기반 투자 스토리 해석하기",
    content: (
      <>
        <P>
          GPT-4o mini가 종목별 최근 1주일 실제 뉴스 헤드라인을 읽고 <Highlight>이 종목에 대해 시장이 지금 무슨 이야기를 믿고 있는지</Highlight>를
          요약한 결과입니다. 재무 필터가 &quot;재무적으로 괜찮은가&quot;를 걸러낸다면, 네러티브 브리프는 &quot;시장이 왜 관심을 갖는지(또는 안 갖는지)&quot;를 알려줍니다.
        </P>
        <H>구성 항목</H>
        <Table
          headers={["항목", "내용"]}
          rows={[
            ["스토리 (Story)", "핵심 투자 스토리 2~3문장 — 이 회사의 장기 성장 동력/사업 구조가 왜 매력적인지(또는 우려되는지)"],
            ["촉매 (Catalysts)", "앞으로 1~3년 스토리에 영향을 줄 요인 최대 3개 — 구조적 성장동력·신사업·정책 변화 등 (단기 실적발표도 포함 가능하나 우선순위는 아님)"],
            ["리스크 (Risks)", "이 장기 스토리가 깨질 수 있는 근본적 리스크 최대 3개"],
            ["시장 단기 관심도", "🔥HOT · 🌤WARM · ❄️COLD — 최근 뉴스량 기준 보조 정보 (판단의 핵심 지표 아님)"],
            ["관심도 전환", "직전 갱신 대비 COLD→WARM 같은 상승 전환이 있으면 배지로 표시"],
          ]}
        />
        <H>한국 종목은 어떻게 다른가</H>
        <P>
          한국 종목은 구글 뉴스 한국어 검색(&quot;종목명 주가 OR 실적&quot;)으로 별도 수집합니다.
          나머지 요약 로직(스토리·촉매·리스크·관심도)은 미국과 동일합니다.
        </P>
        <H>네러티브 브리프의 한계</H>
        <P>
          뉴스 헤드라인 기반이라 <Danger>헤드라인에 없는 내용은 지어내지 않도록</Danger> 프롬프트가 제약돼 있습니다.
          최근 1주일간 뉴스가 없으면 &quot;최근 뉴스 없음&quot;으로 표시되는데, 이는 오류가 아니라
          <Highlight> 시장 관심 밖이라는 정보</Highlight>입니다. 매주 1회만 갱신되므로 그 사이의 급변 이슈는 직접 확인하세요.
        </P>
        <Note>
          💡 네러티브 브리프는 &quot;빠른 1차 검토&quot; 도구입니다. 중요한 포지션을 잡기 전에는 항상 원문 뉴스와 재무제표를 직접 확인하세요.
        </Note>
      </>
    ),
  },
  {
    id: "sector",
    icon: "⊞",
    title: "섹터 분석 — 업종 상대강도와 전환",
    subtitle: "어느 업종을 들여다볼지 가장 먼저 방향을 잡는 화면",
    content: (
      <>
        <P>
          개별 종목이 아니라 <Highlight>업종 단위</Highlight>로 어느 업종이 상대적으로 강한지,
          어느 업종의 흐름이 바뀌고 있는지를 봅니다. 미국은 S&amp;P 500, 한국은 KOSPI를 기준 지수로 삼아 업종별
          수익률을 비교합니다.
        </P>
        <H>업종 지수 소스 — 미국과 한국이 다릅니다</H>
        <Table
          headers={["시장", "소스", "비고"]}
          rows={[
            ["미국", "SPDR 섹터 ETF 11개 (XLK·XLE·XLV 등)", "실제 거래되는 ETF라 실시간성이 좋음"],
            ["한국", "코스피200 섹터지수 (정보기술·금융·헬스케어 등)", "KRX가 직접 산출하는 공식 지수. 유틸리티만 코스피200에 해당 섹터가 없어 업종지수(전기·가스)로 대체"],
          ]}
        />
        <Note>
          💡 화면 상단에 &quot;KRX 공식 지수&quot; 또는 &quot;대표 종목 기준 (폴백)&quot; 배지가 뜹니다.
          KRX 지수를 정상적으로 받아오면 전자, 일시적으로 못 받아오면 대표 종목 몇 개의 평균으로
          대체 계산하고 후자로 표시합니다 — 어느 쪽이든 계산 자체는 정상입니다.
        </Note>
        <H>전환 중인 섹터</H>
        <P>
          <Highlight>3달 상대강도와 최근 1달 상대강도의 방향이 다른</Highlight> 업종을 숫자 그대로 보여줍니다.
          3달은 지수보다 약했는데 최근 1달은 강하면 &quot;돌아서는 중&quot;, 그 반대면 &quot;꺾이는 중&quot;입니다.
          주간 추이에서 최근 2주가 같은 방향이면 &quot;최근 2주 연속&quot; 표시가 붙습니다 — 한 번 튄 것인지
          이어지는 흐름인지 가르는 데 씁니다.
        </P>
        <Table
          headers={["3달 RS", "1달 RS", "읽는 법"]}
          rows={[
            ["+", "+", "이미 자리 잡은 주도 업종"],
            ["−", "+", "막 돌아서는 업종 — 새 아이디어를 찾기 좋은 곳"],
            ["+", "−", "주도 업종이 쉬어가는지 꺾이는지 확인"],
            ["−", "−", "소외 업종"],
          ]}
        />
        <Note>
          💡 예전에 있던 &quot;경기 사이클 판단(회복기·성장기 등)&quot;은 2026-10-20에 뺐습니다. 대표 업종 몇 개의
          1달 수익률 평균으로 국면을 하나로 정하는 방식이라 근거가 약하고, 이 툴의 &quot;단일 판정을 만들지
          않는다&quot; 원칙과도 맞지 않았습니다.
        </Note>
        <H>선행 / 후행 섹터</H>
        <P>
          지수 대비 상대강도가 가장 높은 업종 3개(선행), 가장 낮은 업종 3개(후행)를 보여줍니다.
          최근 4주 추이 표에서 그 흐름이 이번 주만의 일인지 몇 주째 이어지는 추세인지도 확인할 수 있습니다.
        </P>
        <Note>
          💡 섹터 분석은 <Highlight>어디를 볼지</Highlight> 정하는 화면이지 <Highlight>무엇을 살지</Highlight>{" "}
          정하는 화면이 아닙니다. 강한 섹터를 확인했다면 테마 레이더에서 그 안의 세부 테마를 찾아보세요.
        </Note>
      </>
    ),
  },
  {
    id: "radar",
    icon: "📡",
    title: "테마 레이더 — 뉴스·실적·주가 세 축과 6개 라벨",
    subtitle: "종합 점수 없이, 정해진 조합에만 이름을 붙이는 이유",
    content: (
      <>
        <P>
          테마 레이더는 미국·한국 시장의 산업 테마(AI 반도체·데이터센터 전력·조선 등)를
          매주 <Highlight>뉴스·실적·주가 세 축</Highlight>으로 따로 관찰합니다. 섹터 분석이
          &quot;어느 업종이 강한가&quot;라는 큰 그림을 본다면, 테마 레이더는 그 안의 더 세부적인
          산업 테마 단위로 &quot;지금 무슨 일이 벌어지고 있는가&quot;를 봅니다.
        </P>
        <Note>
          💡 세 축을 가중 합산한 점수는 만들지 않습니다. 각 축은 화살표(↑↑/↑/→/↓/–)로만 표시되고,
          정해진 조합에 맞을 때만 라벨을 붙입니다. 억지로 등수를 매기지 않는다는 원칙은
          워치리스트와 동일합니다.
        </Note>
        <H>세 축이 보는 것</H>
        <Table
          headers={["축", "측정 내용", "화살표 기준"]}
          rows={[
            ["뉴스", "이번 주 수집 기사 수 vs 직전 4주 평균", "급증(↑↑)·증가(↑)·보합(→)·감소(↓)"],
            ["실적", "소속 기업 중 매출 YoY 성장률이 \"같은 시장 중앙값\"을 넘는 비율", "과반 초과(↑)·그렇지 않음(↓)·표본부족(–)"],
            ["주가", "소속 기업 주가 수익률 중앙값 vs 시장 지수(미국 S&amp;P 500 / 한국 KOSPI)", "지수 초과(↑)·지수 미달(↓)"],
          ]}
        />
        <H>발견 단계 3그룹 — Quiet · Buzz · Full</H>
        <P>
          라벨 6개는 사실 <Highlight>얼마나 이른 신호인가</Highlight>의 3단계 스펙트럼입니다. 화면도
          그 구조 그대로 세 섹션으로 나뉘어 있고, 각 섹션 제목을 클릭하면 접었다 펼 수 있습니다
          (해당 없는 주에도 섹션 자체는 남아있습니다 — &quot;이번 주는 여기가 비었다&quot;는 것도 정보입니다).
        </P>
        <Table
          headers={["단계", "포함 라벨", "뜻"]}
          rows={[
            ["Quiet — 펀더멘털이 먼저", "Quiet Strength · Quiet Recovery", "실적은 동종보다 앞서는데 뉴스·주가는 조용함. 뉴스만 봐서는 절대 찾을 수 없어서, 이 도구가 존재하는 이유"],
            ["Buzz — 뉴스가 먼저", "Early Buzz · Overheated Buzz", "뉴스가 급증했지만 실적은 아직 안 따라옴. 조기 신호일 수도, 기대만 앞선 것일 수도 있음"],
            ["Full — 삼박자 동반", "Full Alignment · Full Decline", "세 축이 같은 방향으로 움직임. 확인은 됐지만 이미 남들도 아는 구간"],
          ]}
        />
        <Note>
          💡 실적 축은 &quot;매출이 늘었는가&quot;가 아니라 &quot;같은 시장 기업들보다 잘했는가&quot;를
          봅니다. 절대 기준(성장률 &gt; 0)으로 재보니 미국 기업의 92%가 통과해서 거의 모든
          테마가 같은 값이 나왔고, 그래서 2026-09에 시장 중앙값 대비로 바꿨습니다.
          주가 축이 지수 대비 초과수익을 보는 것과 같은 방식입니다 — 대신 시장 전체가
          부진한 국면에서도 상위 테마는 상승으로 나올 수 있다는 점은 감안하세요.
        </Note>
        <Note>
          💡 6개 조합에 안 맞으면 라벨을 억지로 붙이지 않고 화살표만 남깁니다.
          &quot;라벨 없음&quot;은 오류가 아니라 그 자체로 정직한 결과입니다.
        </Note>
        <H>테마 카드를 펼치면</H>
        <P>
          소속 기업의 가치사슬 단계·근거·주력(direct)/일부(partial)/간접(peripheral) 구분·재무 통과
          여부까지 볼 수 있습니다. &quot;재무 통과&quot;는 워치리스트 스크리닝(재무 건전성 필터) 통과
          여부를 그대로 가져온 것입니다. 판정은 항상 <Highlight>통과 / 탈락 / 데이터 부족</Highlight>{" "}
          3분류이며, 탈락일 때는 어떤 기준에 걸렸는지(ROE·F-Score·부채 등)를 배지에 함께
          표시합니다. &quot;미확인&quot;은 <Danger>탈락이 아니라</Danger> 아직 스크리닝 대상이
          된 적이 없다는 뜻입니다(유니버스 밖 종목 등) — 확인 안 된 걸 탈락으로 단정하지 않습니다.
        </P>
        <Note>
          💡 미국·한국 두 시장을 지원합니다 — 상단 탭으로 전환하며, 각 시장은 그 시장의 지수
          (미국 S&amp;P 500 / 한국 KOSPI)와 비교합니다. 한국 유니버스는 시총 3000억 이상(코스피·코스닥 약 650개)이라
          미국보다 작아 소속 기업이 5개 미만인 테마가 많고, 그런 테마는 실적·주가 축이 &quot;–&quot;(표본 부족)로
          남습니다. 홈 화면과 워치리스트 팝업(관련 테마 배지)에서도 이번 주 라벨을 확인할 수 있습니다.
        </Note>
      </>
    ),
  },
  {
    id: "quarterly",
    icon: "🔍",
    title: "분기 리서치 — 재무 신호와 뉴스 비율을 따로 보기",
    subtitle: "\"재무는 이미 움직였는데 시장은 아직 모른다\"를 찾는 화면",
    content: (
      <>
        <P>
          테마 레이더가 매주 갱신되는 반면, 분기 리서치는 <Highlight>분기 재무가 실제로 발표될 때만 갱신됩니다.</Highlight>{" "}
          뉴스·주가는 매주 바뀌지만 재무는 분기에 한 번만 진짜로 바뀌기 때문에, 테마 레이더의
          실적 축보다 더 엄격한 기준으로 &quot;이 테마 소속 기업들의 재무가 실제로 좋아졌는가&quot;만 따로 떼어
          확인하는 화면입니다.
        </P>
        <H>두 축 — 재무 신호와 뉴스 비율</H>
        <Table
          headers={["축", "측정 내용"]}
          rows={[
            ["재무 신호", "테마 소속 기업 중 몇 곳이 \"변화 기업\"으로 판정됐는지 비율. 변화 기업 판정은 매출 전환·매출 흐름·이익 전환 3개 신호 중 하나라도 통과하면 인정"],
            ["뉴스 비율", "이번 분기 주간 평균 뉴스량이 직전 4개 분기 평균 대비 몇 배인지"],
          ]}
        />
        <H>기업별 변화 신호 3개 (O / X / – 로 표시)</H>
        <Table
          headers={["신호", "뜻"]}
          rows={[
            ["매출 전환", "최근 분기 매출이 1년 전 같은 분기보다 일정 비율 이상 늘었는가"],
            ["매출 흐름", "최근 몇 분기 매출 추세가 개선되는 방향인가"],
            ["이익 전환", "영업이익 또는 순이익이 적자에서 흑자로, 또는 뚜렷이 개선됐는가"],
          ]}
        />
        <Note>
          💡 O(통과)·X(통과 못함)·–(데이터부족)를 항상 구분해서 보여줍니다. X와 –를 같은 모양으로
          그리지 않는 이유는, &quot;재무가 나쁘다&quot;와 &quot;재무를 아직 확인 못했다&quot;를 섞으면
          안 되기 때문입니다(원칙: 계산 불가는 탈락이 아니다).
        </Note>
        <H>4칸 분류</H>
        <P>
          재무 신호 비율(높음/낮음)과 뉴스 비율(많음/적음) 두 축을 교차하면 4가지 조합이 나옵니다.
          화면은 이 4칸을 그대로 보여줍니다.
        </P>
        <Table
          headers={["분류", "재무", "뉴스", "뜻"]}
          rows={[
            ["조용한 변화", "높음", "적음", "실적이 먼저 움직였는데 시장은 아직 모릅니다 — 이 화면이 존재하는 이유"],
            ["확인된 변화", "높음", "많음", "재무·뉴스 둘 다 맞았지만 남들도 이미 압니다. 밸류 위치를 꼭 확인하세요"],
            ["기대 선행", "낮음", "많음", "기대가 먼저 붙었습니다. 다음 분기 재무가 따라오는지 지켜볼 구간"],
            ["관심 밖", "낮음", "적음", "이번 분기엔 재무도 뉴스도 특별한 움직임이 없습니다"],
          ]}
        />
        <Note>
          💡 <Highlight>&quot;조용한 변화&quot;가 가장 먼저 볼 가치가 있는 칸</Highlight>입니다. 재무는
          이미 좋아졌는데 뉴스가 조용하다는 건, 아직 시장 가격에 반영되지 않았을 가능성이 있다는 뜻입니다.
        </Note>
        <H>회사별 PSR/PER도 같이 뜹니다</H>
        <P>
          테마를 펼치면 소속 기업별로 변화 신호 3개와 함께 PSR/PER, 밸류 등급이 나옵니다. 계산식은
          워치리스트와 동일하지만, <Highlight>등급을 매기는 기준 집단이 다릅니다</Highlight> — 여기서는
          같은 테마 소속 기업들 안에서 3등분하고, 워치리스트에서는 같은 시장 후보 전체 안에서 3등분합니다.
          같은 종목이 두 화면에서 다른 등급으로 보일 수 있는데, 비교 대상이 다르니 그게 정상입니다.
        </P>
        <Note>
          💡 분기 재무는 실제 공시가 나와야 갱신됩니다(미국 10-Q, 한국 분기보고서 — 대략 분기 말 후
          4~6주 뒤). 방금 분기가 끝났다면 아직 이전 분기 데이터를 보고 있는 것이고, 데이터부족이
          많이 보이는 건 정상입니다.
        </Note>
      </>
    ),
  },
  {
    id: "watchlist",
    icon: "🔖",
    title: "워치리스트 — 후보는 어떻게 뽑히고 순위는 왜 없나",
    subtitle: "필터 통과 종목 전부를 보여주는 이유와 팝업 정보 읽는 법",
    content: (
      <>
        <P>
          워치리스트는 매주 전체 유니버스에 재무 건전성 필터(트랩 필터, 앞 섹션 참고)만 적용해
          <Highlight> 통과한 종목 전부</Highlight>를 후보로 남깁니다. 이전처럼 점수를 매겨 상위 N개로 자르지 않습니다.
          스크리닝 직후 밸류(PSR/PER)·성장(매출 CAGR) 지표까지 같이 계산됩니다(자세한 기준은
          &quot;밸류·성장 지표&quot; 섹션 참고).
        </P>
        <Note>
          💡 왜 순위를 없앴나 — 예전 방식(품질+모멘텀+체제 정합 점수로 상위 50개만)은 스크리닝 시점의 모멘텀에 크게 좌우됐습니다.
          1~3년 보유가 전제라면 그 순간의 모멘텀 순위가 실제 투자 성과와 크게 상관없다고 판단했습니다.
          지금은 재무가 건전한 회사인지만 걸러내고, 그 안에서 어떤 종목을 살지는 밸류·성장·네러티브·섹터 분산·본인의 확신으로 직접 고릅니다.
        </Note>
        <H>필터·검색으로 275종목 좁히기</H>
        <P>
          마켓(미국/한국) 필터, 체제(성장/배당/중립) 필터, &quot;이번 회차 신규만&quot;(직전 회차에 없던 종목만),
          &quot;싼 편만&quot;·&quot;성장만&quot; 필터를 조합해서 쓸 수 있습니다. 이미 아는 종목이 후보에
          있는지 바로 찾고 싶다면 검색창에 티커나 종목명을 입력하면 됩니다(부분 일치, 대소문자 구분 없음).
          모든 필터는 동시에(AND로) 적용됩니다.
        </P>
        <H>신규 · 재진입 배지</H>
        <Table
          headers={["배지", "뜻"]}
          rows={[
            ["신규", "이번 회차에 처음으로 필터를 통과 (또는 이력 기록이 시작된 뒤 처음 확인된 통과)"],
            ["재진입", "예전에 후보였다가 한동안 빠진 뒤 이번에 다시 통과"],
          ]}
        />
        <H>네러티브 브리프 읽는 법 (종목 클릭 팝업)</H>
        <Table
          headers={["항목", "해석"]}
          rows={[
            ["관심도 배지",  "🔥HOT = 뉴스 많은 인기 테마 / 🌤WARM = 꾸준한 관심 / ❄️COLD = 관심 밖 — 보조 정보일 뿐 핵심 지표 아님"],
            ["▲ 관심도 상승", "COLD→WARM 같은 전환 — 시장이 스토리를 발견하기 시작했다는 조기 신호(참고용)"],
            ["스토리",       "최근 1주 뉴스 기반 — 이 회사의 장기 성장 동력이 왜 매력적인지(또는 우려되는지)"],
            ["다가오는 촉매", "앞으로 1~3년 스토리에 영향을 줄 요인 — 구조적 성장동력·신사업·정책 변화 등"],
            ["스토리가 깨지는 경우", "이 리스크가 현실화되는지 계속 확인 — 매도 판단의 기준"],
          ]}
        />
        <Note>
          💡 &quot;최근 뉴스 없음 · COLD&quot;도 정보입니다 — 시장 관심 밖이라는 뜻이므로, 지금 사면 오래 기다릴 각오가 필요합니다.
          마음에 드는 종목은 <Highlight>+ 추가</Highlight> 후 메모에 &quot;왜 담았는지&quot;를 남겨두세요. 나중에 스토리가 아직 유효한지 자문하는 기준이 됩니다.
        </Note>

        <H>정성 체크리스트 (팝업 하단)</H>
        <P>
          네러티브 아래에는 종목별로 독립 저장되는 3개 체크 항목이 있습니다 — 스토리를 한 문장으로 말할 수 있는지,
          스토리가 깨지는 조건을 아는지, 이 스토리가 1년 후에도 유효할 것 같은지(일시적 이슈가 아닌 구조적 동력인지).
          시스템이 자동으로 판정할 수 없는 <Highlight>정성적 판단</Highlight>만 모아뒀습니다 — 재무 필터처럼 숫자로
          이미 검증된 항목은 여기 다시 넣지 않았습니다.
        </P>
        <Note>
          💡 체크는 종목마다 따로 저장되므로 다른 종목을 봐도 섞이지 않습니다. 워치리스트에 추가한 종목은
          팝업 하단에서 매수 이유 메모도 바로 남길 수 있습니다.
        </Note>
      </>
    ),
  },
  {
    id: "faq",
    icon: "?",
    title: "자주 하는 실수와 주의사항",
    subtitle: "이것만 피해도 더 잘 쓸 수 있습니다",
    content: (
      <>
        {[
          {
            q: "시장 단기 관심도(HOT/WARM/COLD)만 보고 판단한다",
            a: "관심도는 최근 1주일 뉴스량 기준 보조 정보일 뿐, 장기 투자 판단의 핵심 지표가 아닙니다. COLD여도 장기 스토리는 탄탄할 수 있고, HOT이라고 재무가 좋은 것도 아닙니다. 판단의 중심은 항상 스토리·촉매·리스크입니다.",
            type: "warn",
          },
          {
            q: "관심도 상승 배지나 테마 레이더의 'Early Buzz' 라벨을 보고 바로 추격 매수한다",
            a: "둘 다 조기 신호일 뿐 매수 신호가 아닙니다. 네러티브 브리프의 촉매·리스크, 테마 카드의 소속 기업 근거를 직접 읽고 정성 체크리스트를 거친 후 본인이 판단하세요.",
            type: "warn",
          },
          {
            q: "'역성장' 배지가 붙으면 무조건 나쁜 종목이라고 생각한다",
            a: "역성장은 재무 부실이 아니라 매출이 줄었다는 사실만 말해줍니다. 재무 건전성 필터는 이미 통과한 종목이라 무차입·흑자인 채로 매출만 줄어든 경우도 많습니다. 밸류가 '싼 편'과 같이 나온다면 이유를 직접 찾아볼 가치가 있는 조합이지, 자동으로 걸러야 할 대상이 아닙니다.",
            type: "warn",
          },
          {
            q: "워치리스트와 분기 리서치의 밸류 등급이 다르게 나오면 오류라고 생각한다",
            a: "PSR 수치 자체는 두 화면이 같은 계산식을 쓰지만, 등급을 매기는 비교 대상이 다릅니다 — 분기 리서치는 같은 테마 안에서, 워치리스트는 같은 시장 후보 전체 안에서 3등분합니다. 비교 집단이 다르면 등급도 다르게 나오는 게 정상입니다.",
            type: "warn",
          },
          {
            q: "테마 레이더에서 '미확인'으로 뜨면 재무가 부실한 종목이다",
            a: "미확인은 탈락이 아닙니다. 워치리스트 스크리닝이 이번 주 그 종목을 갱신 대상으로 다루지 않았거나 애초에 스크리닝 유니버스 밖이라는 뜻일 뿐, 재무를 직접 확인해본 결과가 아닙니다. 판정은 항상 통과/탈락/데이터부족 3분류입니다.",
            type: "warn",
          },
          {
            q: "성적표 수익률이 낮은 구간이 있으면 필터가 틀렸다고 결론짓는다",
            a: "성적표는 사후 검증용이고 표본수(n)가 적으면 노이즈가 큽니다. 이 도구는 1~3년 보유를 전제로 하므로 180일 이상 구간과 표본수를 함께 보고, 짧은 기간(30~90일) 성과만으로 필터를 판단하지 마세요.",
            type: "warn",
          },
          {
            q: "데이터가 '—' 로 나와도 그냥 무시한다",
            a: "— 표시는 해당 파이프라인이 아직 실행되지 않았거나 실패했다는 뜻입니다. 사이드바 맨 아래 칸(누르면 데이터 상태 화면)에서 그 칸이 지연인지 확인하고, 지연이면 GitHub → Actions에서 해당 화면의 워크플로우(섹터 분석은 Weekly Market Analysis, 테마 레이더는 Collect Theme News부터 순서대로)를 수동 재실행하세요.",
            type: "warn",
          },
        ].map(({ q, a, type }) => (
          <div key={q} className="rounded-xl p-3 mt-2" style={{
            background: "#262112",
            border: `1px solid ${type === "danger" ? "#f8717133" : type === "warn" ? "#facc1533" : "#111009"}`,
          }}>
            <p className="text-[12px] font-semibold mb-1" style={{ color: type === "danger" ? "#f87171" : type === "warn" ? "#facc15" : "#ece7d8" }}>
              ✗ {q}
            </p>
            <p className="text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{a}</p>
          </div>
        ))}
      </>
    ),
  },
];

export default function GuideDetailPage() {
  return (
    <div className="space-y-3 max-w-4xl">
      <GuideTabs />
      <PageHeader title="세부 설명서" desc="각 기능의 원리와 해석 방법 · 항목을 눌러서 펼쳐 보세요" />

      <Accordion sections={SECTIONS} />

      <p className="text-[12px] text-center pb-4" style={{ color: "#423e33" }}>
        Undercurrent Sonar는 투자 참고 도구입니다. 최종 투자 판단과 책임은 항상 본인에게 있습니다.
      </p>
    </div>
  );
}
