// 기업 카드 '반대 의견·악재 기사'(2026-11-07, 마스터 플랜 2단계 '반대 논리') - GPT 없이 제목만.
// 구글 뉴스 RSS에서 그 회사 최근 기사를 받아, 부정적인 낱말이 든 제목만 고른다. 요약·평가를 만들지 않고 원문 제목·링크 그대로(원칙 2).
// 낱말 목록은 정한 것뿐 - 걸리는 제목이 반대 논리라는 뜻은 아니고, 리서치 실행 가이드 2-6 "반대 의견 찾기"의 출발점.

export type ContraItem = { title: string; url: string; source: string; date: string; words: string[]; price_only: boolean };

// 주가 등락 낱말 - 이것만 걸린 제목("Stock Falls 0.07% Today", "주가 오늘 하락하는 이유")은 사업 쪽 반대 논리가 아니라 가격 움직임이라
// 뒤로 미루고 몇 건만(2026-11-07 실제 사이트에서 대부분이 이런 제목이었다)
const KR_PRICE = ["하락", "급락", "폭락", "약세", "주가 조정"];
const EN_PRICE = ["falls", "fall", "drop", "drops", "slides", "sinks", "tumbles", "plunge", "plunges", "slump", "slumps", "decline", "declines", "selloff", "sell-off"];
const KR_WORDS = [...KR_PRICE, "부진", "적자", "감소", "우려", "리스크", "위기", "경고", "소송", "제재", "조사", "리콜",
  "하향", "매도 의견", "손실", "악화", "감산", "철수", "중단", "해지", "지연", "논란", "불확실", "둔화", "충격", "과징금", "횡령", "배임",
  "압수수색", "파업", "농성", "철회", "부도", "고평가", "거품", "역성장", "감익", "어닝쇼크", "실적 쇼크"];
// 'cut'만으로는 "cut debt"(부채 감축)도 걸려 전망·목표가 하향 꼴만 본다
const EN_WORDS = [...EN_PRICE, "downgrade", "downgrades", "downgraded", "cuts guidance", "cut guidance", "cuts outlook", "cuts forecast",
  "target cut", "lowers guidance", "lowers outlook", "lowered", "miss", "misses", "weak", "weaker", "warning", "warns", "lawsuit", "sued",
  "probe", "investigation", "recall", "fined", "ban", "sanction", "sanctions", "layoff", "layoffs", "halt", "delay", "delays", "loss", "losses",
  "concern", "concerns", "short seller", "bearish", "sell rating", "underperform", "lower target", "antitrust", "fraud", "strike",
  "overvalued", "bubble", "avoid", "slowdown", "headwinds"];

const enRe = new RegExp(`\\b(${EN_WORDS.map((w) => w.replace(/ /g, "\\s+")).join("|")})\\b`, "gi");

export function negativeWords(title: string, market: string): string[] {
  if (market === "KR") return KR_WORDS.filter((w) => title.includes(w));
  return Array.from(new Set((title.match(enRe) ?? []).map((w) => w.toLowerCase().replace(/\s+/g, " "))));
}

const decode = (s: string) => s.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
  .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&apos;/g, "'").trim();

/** 구글 뉴스 RSS XML -> 기사 목록(제목 끝의 " - 매체명"은 떼어 source로). */
export function parseRss(xml: string): { title: string; url: string; source: string; date: string }[] {
  const out: { title: string; url: string; source: string; date: string }[] = [];
  for (const m of xml.matchAll(/<item>([\s\S]*?)<\/item>/g)) {
    const it = m[1];
    const get = (tag: string) => decode((it.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`)) ?? [])[1] ?? "");
    let title = get("title");
    const source = get("source");
    if (source && title.endsWith(` - ${source}`)) title = title.slice(0, -(source.length + 3));
    const d = new Date(get("pubDate"));
    out.push({ title, url: get("link"), source, date: Number.isNaN(d.getTime()) ? "" : d.toISOString().slice(0, 10) });
  }
  return out;
}

/** 미국 회사 이름에서 검색에 방해되는 꼬리(", Inc."·"Corporation"·"(The)")를 뗀다. */
export function searchName(name: string): string {
  return name.replace(/\s*\(The\)\s*/gi, " ").replace(/,?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Co\.?|Company|Ltd\.?|plc|Holdings?|Group|N\.V\.|S\.A\.)\s*$/gi, "")
    .replace(/,?\s+(Inc\.?|Corporation|Corp\.?)\s*$/gi, "").trim();
}

function isPriceOnly(words: string[], market: string): boolean {
  const price = market === "KR" ? KR_PRICE : EN_PRICE;
  return words.every((w) => price.includes(w));
}

/** 제목에 회사 이름이 있나 - 구글 뉴스는 다른 회사 기사도 섞어 준다(보잉 검색에 "Trump Media Stock Plunge"). */
export function mentions(title: string, name: string, symbol: string, market: string): boolean {
  if (market === "KR") return title.includes(name);
  const first = name.split(/[\s,]+/)[0] ?? "";
  const t = title.toLowerCase();
  return (first.length >= 3 && t.includes(first.toLowerCase())) || new RegExp(`(^|[^A-Za-z])${symbol}([^A-Za-z]|$)`).test(title);
}

const STOP = new Set(["stock", "shares", "the", "and", "for", "with", "after", "amid", "from", "says", "주가", "특징주", "속보", "단독"]);
function tokens(title: string, name: string): Set<string> {
  const nm = name.toLowerCase();
  return new Set(title.toLowerCase().split(/[^0-9a-z가-힣]+/).filter((w) => w.length >= 2 && !STOP.has(w) && !nm.includes(w) && !w.includes(nm)));
}
const overlap = (a: Set<string>, b: Set<string>) => [...a].filter((w) => b.has(w)).length;
const dayDiff = (a: string, b: string) => (a && b ? (Date.parse(a) - Date.parse(b)) / 86400000 : 99);

/** 부정 낱말이 든 제목만. 사업 쪽(하향·소송·중단…)을 먼저, 주가 등락만 걸린 것은 PRICE_MAX건까지. 같은 날 같은 낱말 조합은 같은 사건으로 보고
 *  하나만. 최근 순. */
const PRICE_MAX = 2;
const UP_RE = /\b(jumps?|surges?|soars?|rall(y|ies)|rebounds?|gains?|climbs?|rises?|record high)\b|반등|급등|상승|신고가/i;
export function pickContra(items: { title: string; url: string; source: string; date: string }[], market: string, limit = 6,
                           name = "", symbol = ""): ContraItem[] {
  const seen = new Set<string>();
  const kept: { date: string; toks: Set<string> }[] = [];
  const subst: ContraItem[] = [], price: ContraItem[] = [];
  for (const it of [...items].sort((a, b) => b.date.localeCompare(a.date))) {
    if (name && !mentions(it.title, name, symbol, market)) continue;
    const words = negativeWords(it.title, market);
    if (!words.length) continue;
    const key = it.title.replace(/[\s"'.,:;!?·…\-–—()[\]|]/g, "").slice(0, 24).toLowerCase();
    const toks = tokens(it.title, name);
    // 같은 사건: 제목 앞부분이 같거나, 하루 안쪽에 회사 이름 말고 낱말 둘 이상이 겹침(한화오션 '고공농성'·'중단하라' 기사 5건)
    if (seen.has(key) || kept.some((k) => Math.abs(dayDiff(k.date, it.date)) <= 1 && overlap(k.toks, toks) >= 2)) continue;
    seen.add(key);
    kept.push({ date: it.date, toks });
    const po = isPriceOnly(words, market);
    if (po && UP_RE.test(it.title)) continue;   // "급락 뒤 반등", "Jump After Selloff" - 오른 기사(2026-11-07 실제 사이트)
    (po ? price : subst).push({ ...it, words, price_only: po });
  }
  return [...subst.slice(0, limit), ...price.slice(0, PRICE_MAX)].slice(0, limit);
}
