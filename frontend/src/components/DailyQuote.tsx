"use client";

import { useEffect, useState } from "react";

type Mood = "go" | "caution" | "stop" | "all";
interface Quote { text: string; ko: string; author: string; mood: Mood }

const QUOTES: Quote[] = [
  // ── GO ───────────────────────────────────────────────
  { text: "Be fearful when others are greedy, and greedy when others are fearful.", ko: "남들이 탐욕스러울 때 두려워하고, 남들이 두려워할 때 탐욕스러워져라.", author: "Warren Buffett", mood: "go" },
  { text: "The time of maximum pessimism is the best time to buy.", ko: "비관론이 절정에 달했을 때가 최고의 매수 시점이다.", author: "Sir John Templeton", mood: "go" },
  { text: "Bears make headlines. Bulls make money.", ko: "약세장은 헤드라인을 만들고, 강세장은 돈을 만든다.", author: "Wall Street Proverb", mood: "go" },
  { text: "The trend is your friend until the end when it bends.", ko: "추세는 꺾이기 전까지 당신의 친구다.", author: "Ed Seykota", mood: "go" },
  { text: "In investing, what is comfortable is rarely profitable.", ko: "투자에서 편안한 선택은 좀처럼 수익이 나지 않는다.", author: "Robert Arnott", mood: "go" },
  { text: "It's not whether you're right or wrong, but how much money you make when you're right.", ko: "맞고 틀리고가 중요한 게 아니라, 맞았을 때 얼마나 버느냐가 중요하다.", author: "George Soros", mood: "go" },
  { text: "The stock market is a device for transferring money from the impatient to the patient.", ko: "주식시장은 조급한 자의 돈을 인내심 있는 자에게 이전하는 장치다.", author: "Warren Buffett", mood: "go" },
  { text: "Behind every stock is a company. Find out what it's doing.", ko: "모든 주식 뒤에는 기업이 있다. 그 기업이 무엇을 하는지 파악하라.", author: "Peter Lynch", mood: "go" },
  { text: "Know what you own, and know why you own it.", ko: "무엇을 보유하고 있는지, 왜 보유하는지 알아야 한다.", author: "Peter Lynch", mood: "go" },
  { text: "The intelligent investor is a realist who sells to optimists and buys from pessimists.", ko: "현명한 투자자는 낙관론자에게 팔고 비관론자에게 사는 현실주의자다.", author: "Benjamin Graham", mood: "go" },
  { text: "Price is what you pay. Value is what you get.", ko: "가격은 당신이 지불하는 것이고, 가치는 당신이 얻는 것이다.", author: "Warren Buffett", mood: "go" },
  { text: "In the short run, the market is a voting machine. In the long run, it is a weighing machine.", ko: "단기적으로 시장은 투표기지만, 장기적으로는 저울이다.", author: "Benjamin Graham", mood: "go" },
  { text: "An investment in knowledge pays the best interest.", ko: "지식에 대한 투자가 가장 높은 이자를 돌려준다.", author: "Benjamin Franklin", mood: "go" },
  { text: "The four most dangerous words in investing are: 'this time it's different.'", ko: "투자에서 가장 위험한 네 단어는 '이번엔 다르다'이다.", author: "Sir John Templeton", mood: "go" },
  { text: "Wide diversification is only required when investors do not understand what they are doing.", ko: "지나친 분산투자는 자신이 무엇을 하는지 모를 때나 필요한 것이다.", author: "Warren Buffett", mood: "go" },

  // ── CAUTION ──────────────────────────────────────────
  { text: "Markets can remain irrational longer than you can remain solvent.", ko: "시장은 당신이 버틸 수 있는 것보다 더 오래 비이성적으로 움직일 수 있다.", author: "John Maynard Keynes", mood: "caution" },
  { text: "Risk comes from not knowing what you're doing.", ko: "리스크는 자신이 무엇을 하는지 모르는 데서 온다.", author: "Warren Buffett", mood: "caution" },
  { text: "The first principle is that you must not fool yourself — and you are the easiest person to fool.", ko: "첫 번째 원칙은 자신을 속이지 말라는 것이다. 당신은 속이기 가장 쉬운 사람이기 때문이다.", author: "Richard Feynman", mood: "caution" },
  { text: "It ain't what you don't know that gets you into trouble. It's what you know for sure that just ain't so.", ko: "모르는 것이 문제가 아니라, 틀린 것을 확실히 안다고 믿는 게 문제다.", author: "Mark Twain", mood: "caution" },
  { text: "Uncertainty is the only certainty there is.", ko: "불확실성만이 유일한 확실함이다.", author: "John Allen Paulos", mood: "caution" },
  { text: "Successful investing takes time, discipline and patience.", ko: "성공적인 투자에는 시간, 규율, 그리고 인내가 필요하다.", author: "Charlie Munger", mood: "caution" },
  { text: "The essence of investment management is the management of risks, not the management of returns.", ko: "투자 관리의 본질은 수익 관리가 아니라 리스크 관리다.", author: "Benjamin Graham", mood: "caution" },
  { text: "Lose your opinion, not your money.", ko: "의견을 잃어라, 돈이 아니라.", author: "Trading Maxim", mood: "caution" },
  { text: "Risk is the permanent loss of capital. Danger is the possibility of loss.", ko: "리스크는 자본의 영구적 손실이고, 위험은 손실의 가능성이다.", author: "Howard Marks", mood: "caution" },
  { text: "Without data, you're just another person with an opinion.", ko: "데이터 없이는 당신도 그냥 의견을 가진 한 사람일 뿐이다.", author: "W. Edwards Deming", mood: "caution" },
  { text: "Prediction is very difficult, especially if it's about the future.", ko: "예측은 매우 어렵다. 특히 미래에 관한 것은.", author: "Niels Bohr", mood: "caution" },
  { text: "We don't see things as they are. We see them as we are.", ko: "우리는 사물을 있는 그대로 보지 않는다. 우리 자신이 있는 그대로 본다.", author: "Anaïs Nin", mood: "caution" },
  { text: "The obstacle is the path.", ko: "장애물이 곧 길이다.", author: "Zen Proverb", mood: "caution" },

  // ── STOP ────────────────────────────────────────────
  { text: "Cut your losses short and let your profits run.", ko: "손실은 짧게 끊고, 이익은 길게 달리게 하라.", author: "David Ricardo", mood: "stop" },
  { text: "If you can't stomach a 50% decline in your investment, you shouldn't be in the stock market.", ko: "투자 자산이 50% 하락하는 것을 감당할 수 없다면 주식시장에 있어서는 안 된다.", author: "Warren Buffett", mood: "stop" },
  { text: "Preservation of capital is the first law of investing.", ko: "자본 보전이 투자의 제1법칙이다.", author: "Gerald Loeb", mood: "stop" },
  { text: "When in doubt, stay out.", ko: "의심스러울 땐 빠져나와라.", author: "Trading Maxim", mood: "stop" },
  { text: "Fall seven times, stand up eight.", ko: "일곱 번 넘어져도 여덟 번 일어서라.", author: "Japanese Proverb", mood: "stop" },
  { text: "Success is not final, failure is not fatal: it is the courage to continue that counts.", ko: "성공이 최종적인 것도, 실패가 치명적인 것도 아니다. 중요한 것은 계속할 용기다.", author: "Winston Churchill", mood: "stop" },
  { text: "The impediment to action advances action. What stands in the way becomes the way.", ko: "행동을 막는 것이 행동을 전진시킨다. 길을 막는 것이 곧 길이 된다.", author: "Marcus Aurelius", mood: "stop" },
  { text: "You have power over your mind, not outside events. Realize this, and you will find strength.", ko: "당신은 마음에 대한 힘을 갖고 있지, 외부 사건에 대한 힘이 아니다. 이것을 깨달으면 강해진다.", author: "Marcus Aurelius", mood: "stop" },
  { text: "The stock market is filled with individuals who know the price of everything, but the value of nothing.", ko: "주식시장은 모든 것의 가격은 알지만 가치는 모르는 사람들로 가득하다.", author: "Philip Fisher", mood: "stop" },

  // ── ALL ─────────────────────────────────────────────
  { text: "The unexamined life is not worth living.", ko: "성찰하지 않는 삶은 살 가치가 없다.", author: "Socrates", mood: "all" },
  { text: "We are what we repeatedly do. Excellence, then, is not an act, but a habit.", ko: "우리는 반복적으로 행하는 것의 결과다. 탁월함은 행동이 아니라 습관이다.", author: "Aristotle", mood: "all" },
  { text: "Imagination is more important than knowledge.", ko: "상상력이 지식보다 중요하다.", author: "Albert Einstein", mood: "all" },
  { text: "If you can't explain it simply, you don't understand it well enough.", ko: "단순하게 설명할 수 없다면, 충분히 이해하지 못한 것이다.", author: "Albert Einstein", mood: "all" },
  { text: "The journey of a thousand miles begins with a single step.", ko: "천 리 길도 한 걸음부터.", author: "Lao Tzu", mood: "all" },
  { text: "Our greatest glory is not in never falling, but in rising every time we fall.", ko: "가장 위대한 영광은 한 번도 넘어지지 않는 것이 아니라, 넘어질 때마다 일어나는 것이다.", author: "Confucius", mood: "all" },
  { text: "In God we trust; all others must bring data.", ko: "신은 믿어라. 다른 모든 것은 데이터를 가져와라.", author: "W. Edwards Deming", mood: "all" },
  { text: "The best way to predict the future is to create it.", ko: "미래를 예측하는 가장 좋은 방법은 미래를 만드는 것이다.", author: "Peter Drucker", mood: "all" },
  { text: "Innovation distinguishes between a leader and a follower.", ko: "혁신이 리더와 추종자를 구분한다.", author: "Steve Jobs", mood: "all" },
  { text: "Stay hungry, stay foolish.", ko: "늘 배고프게, 늘 우직하게.", author: "Steve Jobs", mood: "all" },
  { text: "Life must be understood backwards; but it must be lived forwards.", ko: "삶은 거꾸로 이해해야 하지만, 앞으로 살아가야 한다.", author: "Søren Kierkegaard", mood: "all" },
  { text: "A person who never made a mistake never tried anything new.", ko: "실수를 한 번도 하지 않은 사람은 새로운 것을 시도해본 적이 없는 사람이다.", author: "Albert Einstein", mood: "all" },
  { text: "The secret of getting ahead is getting started.", ko: "앞서가는 비결은 시작하는 것이다.", author: "Mark Twain", mood: "all" },
  { text: "It always seems impossible until it's done.", ko: "무언가는 이뤄지기 전까지는 항상 불가능해 보인다.", author: "Nelson Mandela", mood: "all" },
  { text: "He who has a why to live can bear almost any how.", ko: "살아가야 할 이유가 있는 사람은 거의 모든 방법을 견딜 수 있다.", author: "Friedrich Nietzsche", mood: "all" },
];

function pickQuote(): Quote {
  // 2시간마다 변경 (하루 12회) — 전체 명언 풀에서 순환
  const slot = Math.floor(Date.now() / (2 * 3_600_000));
  return QUOTES[slot % QUOTES.length];
}

export default function DailyQuote() {
  // 명언은 시각으로 고르는데, 미리 만들어 둔 페이지(개요 등)는 빌드 시각의 명언을 담고 있어 브라우저 시각과 달라지면
  // React 하이드레이션 오류(#418)가 났다(2026-11-05 사이트 둘러보기). 브라우저에서만 고른다 - 그 전엔 빈 자리.
  const [q, setQ] = useState<Quote | null>(null);
  useEffect(() => setQ(pickQuote()), []);
  if (!q) return <div className="hidden lg:flex flex-1 min-w-0" />;
  const { text, ko, author } = q;
  const accentColor = "#ffb020";

  return (
    <div className="hidden lg:flex items-center gap-3 min-w-0 flex-1">
      <span className="shrink-0 w-[3px] h-7" style={{ background: accentColor, opacity: 0.8 }} />
      <div className="min-w-0">
        <p className="truncate font-semibold leading-snug" style={{ color: "#ece7d8", fontSize: "13px" }}>
          &ldquo;{ko}&rdquo;
          <span className="font-bold ml-2" style={{ color: accentColor, fontSize: "12px" }}>— {author}</span>
        </p>
        <p className="truncate leading-tight" style={{ color: "#726b58", fontSize: "11px" }}>
          {text}
        </p>
      </div>
    </div>
  );
}
