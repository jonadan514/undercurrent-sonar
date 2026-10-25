"use client";

import Link from "next/link";
import GuideTabs from "@/src/components/GuideTabs";
import PageHeader from "@/src/components/PageHeader";

// 투자 실행 가이드 — /guide(기능 설명서)와 역할이 다르다.
// 설명서는 "이 화면이 무엇을 보여주는가", 이 문서는 "그래서 내가 무엇을 하는가"다.
// 종목 추천이나 목표수익률은 쓰지 않는다(이 저장소의 원칙 1과 같은 이유 -
// 화면에 등급이 있으면 사람은 매수 신호로 읽는다).

const ACCENT = "#ffb020";
const GOOD = "#4ade80";
const WARN = "#facc15";
const CAUTION = "#fb923c";
const DANGER = "#f87171";
const INFO = "#6fb3b8";

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[12px] font-bold uppercase tracking-widest mb-2" style={{ color: "var(--text-muted)" }}>
      {children}
    </h2>
  );
}
function Card({ children }: { children: React.ReactNode }) {
  return <div className="bg-card rounded-xl p-5">{children}</div>;
}
function P({ children }: { children: React.ReactNode }) {
  return <p className="text-[12.5px] leading-relaxed mb-2" style={{ color: "var(--text-secondary)" }}>{children}</p>;
}
function Hi({ children }: { children: React.ReactNode }) {
  return <span className="font-semibold" style={{ color: ACCENT }}>{children}</span>;
}
function Box({ color, title, children }: { color: string; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl p-4 mt-3" style={{ background: `${color}0a`, border: `1px solid ${color}2a` }}>
      <p className="text-[12px] font-bold mb-1" style={{ color }}>{title}</p>
      <div className="text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{children}</div>
    </div>
  );
}
function Step({ n, color, title, children }: { n: string; color: string; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl p-4" style={{ background: "var(--bg-inset)", border: `1px solid ${color}33` }}>
      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
        <span className="text-[11px] font-black px-2 py-0.5 rounded shrink-0" style={{ background: `${color}22`, color }}>{n}</span>
        <p className="text-[13px] font-bold text-white">{title}</p>
      </div>
      <div className="text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{children}</div>
    </div>
  );
}
function Checklist({ items }: { items: string[] }) {
  return (
    <div className="space-y-1 mt-2">
      {items.map((t, i) => (
        <div key={i} className="flex items-start gap-2 py-1" style={{ borderBottom: "1px solid #262112" }}>
          <span className="text-[12px] shrink-0 mt-0.5" style={{ color: "var(--text-faint)" }}>☐</span>
          <p className="text-[12px] leading-relaxed" style={{ color: "var(--text-secondary)" }}>{t}</p>
        </div>
      ))}
    </div>
  );
}

export default function PlaybookPage() {
  return (
    <div className="space-y-6 max-w-4xl">

      <GuideTabs />
      <PageHeader title="투자 실행 가이드" desc="발굴부터 매도까지 — 이 툴을 쓰는 사람이 실제로 무엇을 하는가" />

      <Card>
        <P>
          <Hi>사용 설명서와 이 문서는 역할이 다릅니다.</Hi> 설명서는 &quot;이 화면이
          무엇을 보여주는가&quot;를 설명하고, 이 문서는 &quot;그래서 내가 무엇을
          하는가&quot;를 다룹니다. 화면을 다 이해해도 무엇을 살지는 여전히 본인이
          정해야 하는데, 그 과정을 매번 새로 고민하지 않도록 순서로 만들어 둔 것입니다.
        </P>
        <Box color={DANGER} title="먼저 분명히 해둘 것">
          이 문서는 <b>절차</b>이지 <b>조언</b>이 아닙니다. 어떤 종목을 사라거나
          수익이 난다는 이야기는 없습니다. 비중·금액·시점처럼 사람마다 달라야 하는
          건 &quot;정하세요&quot;라고만 쓰고 숫자를 지정하지 않았습니다. 이 툴도
          마찬가지로 매수 신호를 만들지 않습니다 — 화면에 등급이 있으면 사람은
          그걸 신호로 읽기 때문에, 애초에 만들지 않는 쪽을 택한 도구입니다.
        </Box>
      </Card>

      {/* ── 0. 시작 전 ── */}
      <Card>
        <SectionTitle>0단계 · 시작 전에 한 번만 정할 것</SectionTitle>
        <P>
          아래 네 가지를 안 정하고 시작하면, 뒤의 모든 단계가 그때그때 기분에 따라
          흔들립니다. 종이에 적어두고 바꾸고 싶을 때마다 &quot;왜 바꾸는가&quot;를
          같이 적으세요.
        </P>
        <Checklist items={[
          "이 돈은 최소 3년간 쓸 일이 없는 돈인가 — 아니라면 이 툴의 전제(1~3년 보유)와 맞지 않습니다",
          "한 종목에 최대 몇 %까지 넣을 것인가 — 숫자는 본인이 정하되, 정한 뒤에는 확신이 커져도 올리지 않습니다",
          "몇 종목까지 들 것인가 — 분기마다 전부 다시 점검할 수 있는 수여야 합니다. 20종목이면 분기 점검이 하루 일이 됩니다",
          "기록을 어디에 남길 것인가 — 워치리스트 종목 팝업의 메모 칸을 쓰면 종목과 같이 붙어 다닙니다",
        ]} />
        <Box color={WARN} title="왜 기록이 0단계에 있나">
          파는 이유는 살 때의 이유에서 나옵니다. 왜 샀는지 안 적어두면 나중에 팔
          이유도 만들 수 없고, 결국 주가가 오르내리는 것만 보고 결정하게 됩니다.
          이 툴이 끝까지 안 해주는 일이 바로 이것이라, 여기가 전체에서 제일 약한
          고리입니다.
        </Box>
      </Card>

      {/* ── 1. 발굴 ── */}
      <Card>
        <SectionTitle>1단계 · 발굴 — 주 1회 30분</SectionTitle>
        <P>
          매주 같은 요일에 같은 순서로 도는 것이 목적입니다. 새로운 걸 찾아내는 게
          아니라 <Hi>찾을 게 있는지 확인하는</Hi> 시간이고, 대부분의 주에는 아무것도
          안 나오는 게 정상입니다.
        </P>
        <div className="space-y-2 mt-3">
          <Step n="1-1" color={INFO} title="분기 리서치 → 조용한 변화 칸">
            <Link href="/quarterly" className="underline" style={{ color: INFO }}>분기 리서치</Link>에서
            &quot;조용한 변화&quot;에 있는 테마를 봅니다. 재무는 이미 움직였는데 뉴스는
            아직 조용한 칸입니다. 테마를 펼쳐 <b>변화 기업이 몇 곳인지</b>(예: 10/11)
            확인하세요. 소속 기업이 3~4곳뿐이면 비율이 크게 흔들리니 그만큼 덜 믿습니다.
          </Step>
          <Step n="1-2" color={ACCENT} title="테마 레이더 → Quiet 단계">
            <Link href="/radar" className="underline" style={{ color: ACCENT }}>테마 레이더</Link>의
            Quiet(펀더멘털이 먼저) 섹션을 펼칩니다. 1-1과 겹치는 테마가 있으면
            그 테마를 우선으로 봅니다. 두 화면이 다른 데이터(분기 재무 / 주간 3축)로
            같은 결론을 냈다는 뜻이라서요.
          </Step>
          <Step n="1-3" color={GOOD} title="워치리스트 → 재무 통과 + 싸고 + 자라는 것">
            <Link href="/watchlist" className="underline" style={{ color: GOOD }}>워치리스트</Link>에서
            <b> 싼 편만</b> + <b>성장만</b> 필터를 같이 켭니다. 여기 남는 종목은
            &quot;재무 건전 + 후보 중 싼 축 + 매출 3년 연 10% 이상&quot;을 동시에
            만족하는 것들입니다. 여기에 1-1/1-2에서 본 테마 소속 종목이 있으면
            그게 이번 주의 1순위 검토 대상입니다.
          </Step>
          <Step n="1-4" color={CAUTION} title="역성장이 섞여 있으면 따로 메모">
            &quot;싼 편&quot;인데 &quot;역성장&quot;인 종목은 버리지 말고 따로
            적어두세요. 가치 함정일 수도 있지만, 시장이 과하게 깎아놓은 것일 수도
            있습니다. 다만 이건 <b>초보자가 먼저 손댈 자리는 아닙니다</b> — 왜 매출이
            주는지 설명할 수 있어야 하고, 그게 2단계 조사의 난이도를 크게 올립니다.
          </Step>
        </div>
        <Box color={INFO} title="현실적인 기대치">
          이 과정을 거치면 보통 한 주에 <b>0~3개</b>가 남습니다. 0개인 주가 훨씬
          많습니다. 0개인데 억지로 하나 고르는 것이 이 툴을 쓰면서 할 수 있는 가장
          나쁜 행동입니다 — 필터를 통과한 275종목 전부가 후보이지, 매주 뭔가를
          사야 한다는 뜻이 아닙니다.
        </Box>
      </Card>

      {/* ── 2. 기업 조사 ── */}
      <Card>
        <SectionTitle>2단계 · 기업 하나를 보는 순서 — 1~2시간</SectionTitle>
        <P>
          여기가 이 툴이 <Hi>끝나는 지점</Hi>이자 사람이 시작하는 지점입니다. 툴은
          &quot;재무가 건전하고 싸고 자란다&quot;까지만 말해줍니다. 그게 왜 그런지는
          말해주지 않습니다. 순서대로 하되, <b>어느 단계에서든 막히면 거기서 멈추고
          다음 종목으로 넘어가세요.</b> 막힌 걸 뚫는 것보다 다음 후보를 보는 게 거의
          항상 낫습니다.
        </P>

        <div className="space-y-2 mt-3">
          <Step n="2-1" color={INFO} title="뭘 파는 회사인지 한 문장으로 써본다">
            못 쓰겠으면 <b>여기서 중단</b>합니다. &quot;반도체 장비 회사&quot;는
            문장이 아닙니다. &quot;메모리 공장에 들어가는 세정 장비를 만들어
            삼성전자·SK하이닉스에 판다&quot; 정도는 나와야 다음으로 갑니다.
            회사 IR 페이지의 사업 소개 첫 장이면 대개 충분합니다.
          </Step>
          <Step n="2-2" color={INFO} title="돈을 어디서 버는지 쪼개본다">
            매출이 어느 사업부·어느 제품·어느 고객에서 나오는지 봅니다. 한 고객이
            매출의 절반을 넘으면 그 고객의 사정이 곧 이 회사의 사정입니다(그 자체가
            나쁜 건 아니지만 알고 사야 합니다). 사업보고서 또는 분기보고서의
            &quot;사업의 내용&quot;에 있습니다.
          </Step>
          <Step n="2-3" color={GOOD} title="툴이 준 숫자를 확인한다">
            워치리스트에서 종목을 클릭해 팝업을 엽니다. 여기 있는 숫자는 이미
            계산돼 있으니 읽기만 하면 됩니다.
            <Checklist items={[
              "F-Score 몇 점인가 (6점 미만은 애초에 후보에 없습니다)",
              "부채비율·이자보상배율 — '무차입'이면 좋은 상태, '자본잠식'이면 원인을 반드시 확인",
              "PSR / PER — 같은 시장 후보 중 어느 위치인지",
              "매출 3년 CAGR / 최근 1년 — 3년은 낮은데 1년이 높으면 최근에 꺾여 올라온 것이고, 반대면 둔화 중입니다",
              "영업이익률 방향 — '악화'면 매출이 늘어도 남는 게 줄고 있다는 뜻",
            ]} />
          </Step>
          <Step n="2-4" color={ACCENT} title="'왜 싼가'와 '왜 자라는가'에 내가 답해본다">
            이게 이 단계의 핵심입니다. 툴은 싸다는 <b>사실</b>만 알려주고 <b>이유</b>는
            모릅니다. 싼 데는 항상 이유가 있습니다 — 업황이 꺾였거나, 큰 고객을
            잃었거나, 소송이 걸렸거나, 아니면 그냥 아직 아무도 안 봤거나.
            <br /><br />
            <b>답을 못 찾으면 산 게 아니라 주운 것입니다.</b> 최근 실적 발표 자료와
            최근 3~6개월 뉴스를 훑으면 대개 나옵니다. 워치리스트 팝업의 네러티브
            브리프가 1차 요약을 해주지만, 그건 최근 1주 헤드라인 기반이라 시작점일
            뿐입니다.
          </Step>
          <Step n="2-5" color={CAUTION} title="깨지는 조건 3개를 적는다">
            &quot;이게 사실이 되면 내 판단이 틀린 것&quot; 3개를 구체적으로 씁니다.
            나중에 이게 그대로 <b>매도 기준</b>이 됩니다.
            <br /><br />
            좋은 예: &quot;주 고객사가 내년 설비투자를 줄인다고 공시하면&quot;,
            &quot;영업이익률이 2분기 연속 떨어지면&quot;, &quot;경쟁사가 같은 제품을
            더 싸게 내놓으면&quot;.
            <br />
            나쁜 예: &quot;주가가 20% 빠지면&quot; — 이건 회사에 대한 판단이 아니라
            가격에 대한 반응입니다.
          </Step>
          <Step n="2-6" color={DANGER} title="반대 의견을 일부러 찾는다">
            &quot;왜 남들은 이걸 안 사는가&quot;를 20분만 찾아보세요. 종목토론방이
            아니라 증권사 리포트나 기사에서요. 반대 논리를 하나도 못 찾았다면
            대개는 <b>충분히 안 찾아본 것</b>입니다. 찾은 반대 논리가 2-5의 깨지는
            조건과 겹치면 그건 진짜 리스크입니다.
          </Step>
        </div>

        <Box color={WARN} title="2단계에서 가장 흔한 실수">
          툴이 통과시켰다는 이유로 2-1~2-6을 건너뛰는 것입니다. 재무 필터는
          <b> 명백히 부실한 회사를 걸러내는 수비 장치</b>지, 좋은 회사를 골라주는
          장치가 아닙니다. 275개 후보 전부가 이 필터를 통과했다는 걸 기억하세요.
        </Box>
      </Card>

      {/* ── 3. 매수 ── */}
      <Card>
        <SectionTitle>3단계 · 살 때</SectionTitle>
        <P>
          2단계를 통과했다면 이제 살지 말지를 정합니다. 여기서 툴이 해주는 건
          없습니다 — 얼마를, 언제, 몇 번에 나눠 살지는 전적으로 본인 몫입니다.
        </P>
        <Checklist items={[
          "0단계에서 정한 '한 종목 최대 비중'을 넘지 않는가 — 확신이 크다는 이유로 올리지 않습니다",
          "한 번에 다 사지 않고 나눠 사는가 — 내 판단이 틀렸을 때 고칠 여지를 남기는 것이지, 평균단가를 낮추려는 게 아닙니다",
          "이 종목이 이미 가진 종목들과 같은 테마·같은 고객에 묶여 있지 않은가 — 다섯 종목이 전부 메모리 업황에 달려 있으면 한 종목을 다섯 번 산 것과 같습니다",
          "매수 직후 메모를 남겼는가 — 날짜·가격·왜 샀는지 3줄·깨지는 조건 3개",
        ]} />
        <Box color={INFO} title="메모는 워치리스트 팝업에">
          <Link href="/watchlist" className="underline" style={{ color: INFO }}>워치리스트</Link>에서
          종목을 <b>+ 추가</b>한 뒤 팝업 하단 메모 칸에 적으면 종목과 함께 남습니다.
          지금 이 툴에는 매수가·수량을 넣는 칸이 따로 없어서, 메모 첫 줄에
          &quot;2026-10-02 / 12,300원 / 10주&quot;처럼 같이 적어두는 게 현실적입니다.
        </Box>
      </Card>

      {/* ── 4. 보유 중 ── */}
      <Card>
        <SectionTitle>4단계 · 들고 있는 동안 — 분기 1회</SectionTitle>
        <P>
          매일 보지 않는 것이 이 단계의 전부입니다. 점검은 <Hi>분기 재무가 새로
          나왔을 때</Hi> 합니다(미국 10-Q, 한국 분기보고서 — 분기 말 후 4~6주).
          그때가 실제로 새로운 정보가 들어오는 유일한 시점입니다.
        </P>
        <Checklist items={[
          "내가 적어둔 '깨지는 조건 3개' 중 현실이 된 게 있는가 — 이것만 먼저 봅니다",
          "분기 리서치에서 그 테마가 여전히 '조용한 변화' 또는 '확인된 변화'에 있는가, '관심 밖'으로 내려갔는가",
          "워치리스트에서 성장 등급이 성장 → 정체 → 역성장으로 내려가지 않았는가",
          "영업이익률 방향이 '개선'에서 '악화'로 바뀌지 않았는가",
          "밸류 등급이 '싼 편'에서 '비싼 편'으로 올라갔는가 — 스토리가 유효한데 비싸진 것이면 정상입니다(시장이 뒤늦게 알아본 것)",
          "분기 사이에 계약 해지·8-K 주의(붉은 칸)·실적 발표 같은 일이 있었는가 — 내 관심에 넣어 두면 매주 브리핑 맨 위 '⭐ 관심 종목에 생긴 일'에 모입니다",
        ]} />
        <Box color={DANGER} title="점검할 때 보지 말아야 할 것">
          <b>주가와 평가손익.</b> 이 단계의 질문은 &quot;회사가 내 생각대로 가고
          있는가&quot;이지 &quot;지금 얼마 벌었나&quot;가 아닙니다. 손익을 먼저 보면
          그 다음 판단이 전부 거기에 끌려갑니다. 굳이 순서를 정하자면 위 항목을 다
          확인한 뒤에 보세요.
        </Box>
      </Card>

      {/* ── 5. 매도 ── */}
      <Card>
        <SectionTitle>5단계 · 팔 때 — 세 가지 경우만</SectionTitle>
        <div className="space-y-2 mt-1">
          {[
            { n: "①", t: "적어둔 깨지는 조건이 현실이 됐다", d: "2-5에서 적은 그대로입니다. 그래서 그때 구체적으로 적어야 했습니다." },
            { n: "②", t: "살 때의 이유가 더 이상 사실이 아니다", d: "조건까지 깨지진 않았지만 전제가 바뀐 경우입니다. 예: 싸서 샀는데 이제 안 싸고, 그 사이 성장도 멈췄다." },
            { n: "③", t: "더 확신 있는 곳에 이 돈이 필요하다", d: "현금이 무한하지 않으니 생기는 이유입니다. 다만 '새로 발견한 게 더 좋아 보인다'는 느낌과, 2단계를 다 거친 확신은 다릅니다." },
          ].map(({ n, t, d }) => (
            <div key={n} className="flex items-start gap-3 rounded-xl p-3" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
              <span className="text-sm font-black shrink-0 w-5 text-center" style={{ color: GOOD }}>{n}</span>
              <div>
                <p className="text-[12.5px] font-semibold text-white">{t}</p>
                <p className="text-[12px] mt-0.5" style={{ color: "var(--text-muted)" }}>{d}</p>
              </div>
            </div>
          ))}
        </div>
        <Box color={DANGER} title="매도 사유가 아닌 것">
          주가가 떨어져서 · 주가가 올라서 · 오래 들고 있었는데 안 올라서 ·
          다른 사람이 팔아서 · 시장 전체가 빠져서. 전부 회사에 대한 판단이 아니라
          가격에 대한 반응입니다. 이 툴이 단기 타이밍 지표를 전부 걷어낸 이유이기도
          합니다.
        </Box>
      </Card>

      {/* ── 이 툴이 안 해주는 것 ── */}
      <Card>
        <SectionTitle>이 툴이 답해주지 않는 것</SectionTitle>
        <P>
          아래는 전부 사람이 해야 하는 판단입니다. 툴에 없다고 생략하면 안 되는
          것들이라 따로 적어둡니다.
        </P>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
          {[
            ["얼마나 살지", "비중·금액은 본인의 자금 사정과 확신의 정도에 달렸습니다"],
            ["언제 살지", "타이밍 지표를 의도적으로 전부 제거한 도구입니다"],
            ["경영진이 믿을 만한지", "과거 약속을 지켰는지, 주주에게 어떻게 했는지 — 숫자 밖의 문제"],
            ["이 산업이 5년 뒤에도 있을지", "구조적 변화는 재무제표에 늦게 나타납니다"],
            ["지금 시장 전체가 비싼지", "섹터 분석은 업종 간 상대 비교지 시장의 절대 수준이 아닙니다"],
            ["내가 산 종목이 지금 어떤지", "성적표는 '후보'를 추적하지 '내 보유'를 추적하지 않습니다"],
          ].map(([t, d]) => (
            <div key={t} className="rounded-xl p-3" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
              <p className="text-[12px] font-semibold text-white mb-0.5">{t}</p>
              <p className="text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{d}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* ── 함정 ── */}
      <Card>
        <SectionTitle>초보자가 특히 빠지기 쉬운 함정</SectionTitle>
        <div className="space-y-2 mt-1">
          {[
            {
              q: "'싼 편만' 필터만 켜고 거기서 고른다",
              a: "재무 건전 + 싸다 = 좋은 종목이 아닙니다. 매출이 3년째 줄어서 시장이 싸게 매긴 것일 수 있고, 그게 정확히 가치 함정입니다. 성장 축을 같이 켜거나, 최소한 성장 등급을 확인하세요. 이 툴에 성장 축이 추가된 이유가 바로 이 구멍 때문입니다.",
            },
            {
              q: "테마가 좋아 보여서 그 안의 아무 종목이나 산다",
              a: "테마가 맞아도 그 테마에서 돈을 버는 회사는 일부입니다. 테마 카드를 펼치면 소속 기업이 '주력(direct)'인지 '간접(peripheral)'인지 나옵니다. 간접이면 테마가 잘 돼도 이 회사 실적에는 거의 안 옵니다.",
            },
            {
              q: "뉴스에 많이 나와서 산다",
              a: "이 툴은 정확히 그 반대를 하려고 만들어졌습니다. 뉴스가 많다(Buzz·확인된 변화)는 건 이미 남들도 안다는 뜻이고, 가격에 반영돼 있을 가능성이 큽니다. 뉴스가 조용한데 재무가 움직인 자리(Quiet·조용한 변화)가 이 도구가 찾으려는 곳입니다.",
            },
            {
              q: "떨어져서 더 산다(물타기)",
              a: "추가 매수의 근거는 가격이 아니라 '판단이 여전히 맞다는 새로운 확인'이어야 합니다. 분기 재무가 다시 좋게 나왔다면 근거지만, 그냥 싸졌다는 건 근거가 아닙니다. 0단계에서 정한 최대 비중을 물타기로 넘기는 건 가장 흔한 사고 경로입니다.",
            },
            {
              q: "필터 기준을 내 종목에 맞춰 바꾼다",
              a: "'이 종목은 F-Score 5점인데 괜찮아 보이니 기준을 5로 낮추자'가 시작입니다. 기준을 바꿀 거면 특정 종목을 보기 전에, 그리고 결과(성적표)를 근거로 바꿔야 합니다. 다만 성적표는 2027년 2월쯤 되어야 판단할 만한 데이터가 쌓입니다.",
            },
            {
              q: "매주 뭔가를 사야 한다고 느낀다",
              a: "아무것도 안 사는 주가 대부분인 게 정상입니다. 이 툴은 매주 후보를 보여주지만 그건 '검토 대상'이지 '이번 주의 추천'이 아닙니다.",
            },
          ].map(({ q, a }) => (
            <div key={q} className="rounded-xl p-3" style={{ background: "#262112", border: `1px solid ${WARN}33` }}>
              <p className="text-[12px] font-semibold mb-1" style={{ color: WARN }}>✗ {q}</p>
              <p className="text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{a}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* ── 첫 3개월 ── */}
      <Card>
        <SectionTitle>처음 3개월은 이렇게</SectionTitle>
        <div className="space-y-2">
          {[
            { m: "1개월차", c: INFO, t: "사지 않고 보기만 합니다", d: "매주 1단계 루틴만 돌면서 후보가 어떻게 바뀌는지 봅니다. 마음에 드는 종목이 나오면 2단계 조사를 끝까지 해보되, 사지는 않고 메모만 남깁니다. 4주 뒤에 그 메모를 다시 읽으면 자기 판단의 버릇이 보입니다." },
            { m: "2개월차", c: WARN, t: "가장 확신 있는 하나만, 정한 비중의 절반만", d: "2단계를 통과한 것 중 제일 자신 있는 하나를 고릅니다. 한 번에 정한 비중을 다 채우지 말고 절반만 삽니다. 목적은 수익이 아니라 '내가 실제로 이 과정을 끝까지 하는가'를 확인하는 것입니다." },
            { m: "3개월차", c: GOOD, t: "첫 분기 점검을 해봅니다", d: "분기 재무가 나오면 4단계 점검을 그대로 해봅니다. 내가 적어둔 깨지는 조건이 실제로 판단에 쓸 만했는지가 여기서 드러납니다. 쓸모없는 조건을 적었다면 그게 3개월간 배운 가장 큰 것입니다." },
          ].map(({ m, c, t, d }) => (
            <div key={m} className="rounded-xl p-4" style={{ background: "var(--bg-inset)", border: `1px solid ${c}33` }}>
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <span className="text-[11px] font-black px-2 py-0.5 rounded shrink-0" style={{ background: `${c}22`, color: c }}>{m}</span>
                <p className="text-[13px] font-bold text-white">{t}</p>
              </div>
              <p className="text-[12px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{d}</p>
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
