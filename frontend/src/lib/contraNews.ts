// 기업 카드 '반대 의견·악재 기사'(2026-11-07, 마스터 플랜 2단계 '반대 논리') - GPT 없이 제목만.
// 구글 뉴스 RSS에서 그 회사 최근 기사를 받아, 부정적인 낱말이 든 제목만 고른다. 요약·평가를 만들지 않고 원문 제목·링크 그대로(원칙 2).
// 낱말 목록은 정한 것뿐 - 걸리는 제목이 반대 논리라는 뜻은 아니고, 리서치 실행 가이드 2-6 "반대 의견 찾기"의 출발점.

export type ContraItem = { title: string; url: string; source: string; date: string; words: string[] };

const KR_WORDS = ["하락", "급락", "폭락", "약세", "부진", "적자", "감소", "우려", "리스크", "위기", "경고", "소송", "제재", "조사", "리콜",
  "하향", "매도", "손실", "악화", "감산", "철수", "중단", "해지", "지연", "논란", "불확실", "둔화", "충격", "과징금", "횡령", "배임",
  "압수수색", "파업", "철회", "부도", "고평가", "거품", "역성장", "감익", "어닝쇼크", "실적 쇼크"];
const EN_WORDS = ["downgrade", "downgrades", "downgraded", "cut", "cuts", "falls", "fall", "plunge", "plunges", "slump", "slumps", "drop",
  "drops", "decline", "declines", "miss", "misses", "weak", "weaker", "warning", "warns", "lawsuit", "sued", "probe", "investigation",
  "recall", "fine", "fined", "ban", "sanction", "sanctions", "layoff", "layoffs", "halt", "delay", "delays", "loss", "losses", "concern",
  "concerns", "short seller", "bearish", "sell rating", "underperform", "lower target", "lowers", "antitrust", "fraud", "strike",
  "overvalued", "bubble", "avoid", "slowdown", "headwinds", "tumbles", "sinks", "slides"];

const enRe = new RegExp(`\\b(${EN_WORDS.map((w) => w.replace(/ /g, "\\s+")).join("|")})\\b`, "gi");

export function negativeWords(title: string, market: string): string[] {
  if (market === "KR") return KR_WORDS.filter((w) => title.includes(w));
  return Array.from(new Set((title.match(enRe) ?? []).map((w) => w.toLowerCase())));
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

/** 부정 낱말이 든 제목만, 같은 제목 앞부분이 겹치는 것은 하나로, 최근 순. */
export function pickContra(items: { title: string; url: string; source: string; date: string }[], market: string, limit = 6): ContraItem[] {
  const seen = new Set<string>();
  const out: ContraItem[] = [];
  for (const it of [...items].sort((a, b) => b.date.localeCompare(a.date))) {
    const words = negativeWords(it.title, market);
    if (!words.length) continue;
    const key = it.title.replace(/[\s"'.,:;!?·…\-–—()[\]|]/g, "").slice(0, 24).toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ ...it, words });
    if (out.length >= limit) break;
  }
  return out;
}
