"use client";

import { useEffect, useState, useCallback } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { themeName } from "@/src/lib/themeNames";
import { useMarket } from "@/src/contexts/MarketContext";
import { krStockName } from "@/src/lib/krStockNames";
import Link from "next/link";
import StockLink from "@/src/components/StockLink";
import AsOf from "@/src/components/AsOf";
import { LABEL_KO, labelWithKo } from "@/src/lib/labelNames";
import PageHeader from "@/src/components/PageHeader";
import EmptyState from "@/src/components/EmptyState";
import Note from "@/src/components/Note";

// globals.css의 앱 전역 토큰을 그대로 쓴다 (워치리스트 페이지와 같은 터미널·앰버 룩).
const ACCENT = "var(--accent)";
const ACCENT_SOFT = "rgba(255,176,32,0.14)";
const GOOD = "var(--good)";
const GOOD_SOFT = "rgba(74,222,128,0.14)";
const DANGER = "var(--danger)";
const DANGER_SOFT = "rgba(248,113,113,0.14)";
const MUTED = "var(--text-muted)";
const MUTED_SOFT = "rgba(139,130,113,0.14)";
const FAINT = "var(--text-faint)";
const MONO = 'ui-monospace, "SF Mono", "Cascadia Code", "Roboto Mono", monospace';

type Arrow = "up2" | "up1" | "flat" | "down" | "na" | null;

interface ThemeSignal {
  theme_id: string;
  news_count: number | null;
  news_baseline: number | null;
  news_ratio: number | null;
  news_arrow: Arrow;
  earn_members: number | null;
  earn_improved: number | null;
  earn_insufficient: number | null;
  earn_ratio: number | null;
  earn_arrow: Arrow;
  earn_as_of: string | null;
  price_median_ret: number | null;
  price_index_ret: number | null;
  price_excess: number | null;
  price_volume_ratio: number | null;
  earn_surprise_n: number | null;
  earn_surprise_beat: number | null;
  earn_surprise_ratio: number | null;
  earn_surprise_median: number | null;
  price_arrow: Arrow;
  label: string | null;
  member_count: number | null;
}

interface Member {
  ticker: string;
  stage: string | null;
  evidence: string | null;
  linkage: string;
  confidence: string;
  flagged: number;
  other_themes: string[];
  other_perceived?: string[];  // 다른 테마에 "시장 인식"으로만 걸린 것 - 사업 소속과 구분해 표시
  finance: { status: string; piotroski: number | null; reasons?: string[] };
}

// 소속 기업 이벤트(2026-10-21, /api/radar/events) - 한국 공시·미국 8-K·내부자 장내 매수를 테마 소속(direct+partial)으로 묶은 것.
// 세 축의 화살표·라벨에 들어가지 않는다 - 옆에 놓는 건수와 공시 원문 값(점수 아님).
interface ThemeEventItem { date: string; ticker: string; name?: string | null; type: "disclosure" | "insider"; kind: string;
  text: string; warn: boolean; url?: string | null; value?: number | null; excerpt?: string | null }
// 주별 변화(2026-10-21): weeks = [이번 주, 1주 전 ... 4주 전], 데이터가 없던 주는 null. avg = 데이터 있던 직전 주 평균(2주 미만이면 null).
// busier = 이번 주가 평소의 2배 이상이면서 최소 건수(공시 3·내부자 2개사) 이상 - 조건 일치일 뿐 점수·라벨 아님.
interface WeeklyCount { weeks: (number | null)[]; base_weeks: number; avg: number | null }
interface ThemeEvents {
  counts: { disclosure_7d: number; disclosure_30d: number; warn_30d: number; insider_cos_7d: number; insider_cos_30d: number;
            companies_30d: number; members: number;
            weekly?: { disclosure: WeeklyCount; insider: WeeklyCount }; busier?: { disclosure: boolean; insider: boolean } };
  items: ThemeEventItem[];
}
// "축은 조용" 칸 순서 - 주별 변화가 있으면 이번 주 공시가 평소의 몇 배인지(평소 0이면 1로 나눔), 없으면 이벤트 있던 소속 기업 수.
// 공시 숫자를 그대로 나눈 값일 뿐 점수가 아니다.
const quietOrder = (ev?: ThemeEvents) => {
  const w = ev?.counts.weekly?.disclosure;
  return w && w.avg != null ? (w.weeks[0] ?? 0) / Math.max(w.avg, 1) : ev?.counts.companies_30d ?? 0;
};
const hasRecent = (ev?: ThemeEvents) => !!ev && (ev.counts.disclosure_7d > 0 || ev.counts.insider_cos_7d > 0);
const isBusier = (ev?: ThemeEvents) => !!ev?.counts.busier && (ev.counts.busier.disclosure || ev.counts.busier.insider);
const avgText = (w?: WeeklyCount) => w?.avg == null ? "" : `·평소 ${w.avg < 10 ? w.avg.toFixed(1) : Math.round(w.avg)}`;

function EventChip({ ev }: { ev?: ThemeEvents }) {
  if (!hasRecent(ev)) return null;
  const c = ev!.counts;
  const b = c.busier;
  const parts: [string, boolean][] = [];
  if (c.disclosure_7d > 0) parts.push([`공시 ${c.disclosure_7d}${avgText(c.weekly?.disclosure)}`, !!b?.disclosure]);
  if (c.insider_cos_7d > 0) parts.push([`내부자 매수 ${c.insider_cos_7d}개사${avgText(c.weekly?.insider)}`, !!b?.insider]);
  const busy = parts.some(([, x]) => x);
  return (
    <span className="whitespace-nowrap rounded-md px-2 py-0.5 text-[11.5px]"
      title={"최근 7일 소속 기업 공시·내부자 장내 매수 (세 축과 별개). 평소 = 직전 4주 주당 평균" + (busy ? " · 굵은 항목은 평소의 2배 이상" : "")}
      style={{ border: `1px solid ${busy ? ACCENT + "88" : "var(--border-ctrl)"}`, color: "var(--text-secondary)", fontFamily: MONO }}>
      📄 {parts.map(([t, x], i) => (
        <span key={i}>{i > 0 && " · "}<span style={x ? { color: ACCENT, fontWeight: 700 } : undefined}>{t}</span></span>
      ))}
    </span>
  );
}

function WeekRow({ label, w, unit }: { label: string; w?: WeeklyCount; unit: string }) {
  if (!w) return null;
  const names = ["이번 주", "1주 전", "2주 전", "3주 전", "4주 전"];
  return (
    <div className="flex flex-wrap gap-x-2 text-[11.5px]" style={{ color: MUTED, fontFamily: MONO }}>
      <span style={{ color: FAINT }}>{label}</span>
      {w.weeks.map((n, i) => (
        <span key={i} style={i === 0 ? { color: "var(--text-primary)", fontWeight: 700 } : undefined}>
          {names[i]} {n == null ? "–" : `${n}${unit}`}
        </span>
      ))}
      <span style={{ color: FAINT }}>{w.avg == null ? "· 비교 기준 부족(데이터 2주 미만)" : `· 평소 주 ${w.avg}${unit}`}</span>
    </div>
  );
}

function eventMoney(v: number | null | undefined, market: string): string {
  if (v == null) return "";
  if (market === "KR") return v >= 1e8 ? `${(v / 1e8).toFixed(1)}억원` : `${Math.round(v / 1e4).toLocaleString()}만원`;
  return v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : `$${Math.round(v / 1e3).toLocaleString()}K`;
}

function EventList({ ev, market }: { ev?: ThemeEvents; market: string }) {
  if (!ev || ev.items.length === 0) return null;
  const c = ev.counts;
  return (
    <div className="mt-3 rounded-lg px-3 py-2" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
      <p className="text-[12px] font-semibold" style={{ color: MUTED }}>
        소속 기업 이벤트 (최근 30일) — 공시 {c.disclosure_30d}건 · 내부자 매수 {c.insider_cos_30d}개사 · 소속 {c.members}개 중 {c.companies_30d}개사
      </p>
      {c.weekly && (
        <div className="mt-1 space-y-0.5">
          <WeekRow label="공시" w={c.weekly.disclosure} unit="건" />
          <WeekRow label="내부자" w={c.weekly.insider} unit="개사" />
        </div>
      )}
      <div className="mt-1.5 space-y-1">
        {ev.items.map((e, i) => (
          <div key={`${e.ticker}-${e.date}-${i}`} className="text-[12px]">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span style={{ color: FAINT, fontFamily: MONO }}>{e.date.slice(5).replace("-", "/")}</span>
              <StockLink market={market} symbol={e.ticker} className="font-bold" style={{ color: "var(--text-primary)" }}>
                {e.name || (market === "KR" ? krStockName(e.ticker) : null) || e.ticker}
              </StockLink>
              <span style={{ color: e.warn ? "#f87171" : e.type === "insider" ? "#4ade80" : "var(--text-secondary)" }}>{e.kind}</span>
              <span style={{ color: MUTED }}>{e.text}{e.value != null ? ` · ${eventMoney(e.value, market)}` : ""}</span>
              {e.url && <a href={e.url} target="_blank" rel="noreferrer" className="text-[11px] hover:underline" style={{ color: FAINT }}>원문↗</a>}
            </div>
            {e.excerpt && <p className="text-[12px] line-clamp-1" style={{ color: FAINT }} title={e.excerpt}>{e.excerpt}</p>}
          </div>
        ))}
      </div>
      <Note>{market === "KR" ? "DART 공급계약·계약 해지·계약금액 정정·잠정실적" : "SEC 8-K(실적 발표만 있는 것 제외)"} · 내부자 장내 매수 · 세 축 계산에는 들어가지 않습니다</Note>
    </div>
  );
}

interface Article {
  title: string;
  url: string;
  source: string | null;
  published_at: string | null;
}

const INFO = "var(--info)";
const INFO_SOFT = "rgba(111,179,184,0.15)";

// SPEC §6.2 - 순위가 아니라 편집 방침.
//
// 2026-09 화면 개편: 6개 라벨이 사실 "얼마나 이른 신호인가"의 3단계
// 스펙트럼이라는 걸 화면 구조로 드러낸다. Quiet(펀더멘털이 먼저 - 시장이
// 아직 모름) -> Buzz(뉴스가 먼저) -> Full(삼박자 동반 - 이미 알려짐).
// 이름에만 있던 구조를 섹션으로 만들어, 어느 단계를 보고 있는지가 보이게 함.
const STAGES = [
  {
    key: "quiet",
    name: "Quiet — 펀더멘털이 먼저",
    when: "발견 단계 1/3 · 시장이 아직 안 움직임",
    color: "var(--accent)",
    labels: ["Quiet Strength", "Quiet Recovery"],
    desc: "실적은 동종보다 앞서는데 뉴스·주가는 조용한 테마. 뉴스만 봐서는 찾을 수 없어서, 이 툴이 존재하는 이유입니다.",
  },
  {
    key: "buzz",
    name: "Buzz — 뉴스가 먼저",
    when: "발견 단계 2/3 · 관심은 붙었고 실적은 미확인",
    color: INFO,
    labels: ["Early Buzz", "Overheated Buzz"],
    desc: "뉴스가 급증했지만 실적이 아직 안 따라온 테마. 조기 신호일 수도, 기대만 앞선 것일 수도 있습니다.",
  },
  {
    key: "full",
    name: "Full — 삼박자 동반",
    when: "발견 단계 3/3 · 이미 알려진 상태",
    color: "var(--text-secondary)",
    labels: ["Full Alignment", "Full Decline"],
    desc: "세 축이 같은 방향으로 움직이는 테마. 확인은 됐지만 남들도 이미 아는 구간입니다.",
  },
] as const;

// 강조는 오직 배지로만 한다(카드 모양은 라벨과 무관하게 동일). 라벨이 많은
// 주에도 화면이 줄무늬처럼 되지 않으면서, 배지 강도가 "얼마나 이른 신호인가"와
// 그대로 대응한다.
const BADGE_STYLE: Record<string, React.CSSProperties> = {
  "Quiet Strength": { background: "var(--accent)", color: "#000" },                                    // 이 툴의 존재 이유 - 유일하게 채운 색
  "Quiet Recovery": { color: "var(--accent)", boxShadow: "inset 0 0 0 1.5px var(--accent)" },          // 같은 그룹, 한 단계 약하게
  "Early Buzz": { background: INFO_SOFT, color: INFO },
  "Overheated Buzz": { background: INFO_SOFT, color: INFO },
  "Full Alignment": { background: MUTED_SOFT, color: "var(--text-secondary)" },                        // 이미 알려진 구간 - 가장 약하게
  "Full Decline": { background: MUTED_SOFT, color: "var(--text-secondary)" },
};

const LABEL_NOTE: Record<string, string> = {
  "Quiet Strength": "뉴스는 잠잠하거나 줄었는데 실적은 동종 대비 앞선 테마.",
  "Quiet Recovery": "뉴스도 주가도 안 좋은데 실적은 앞선 테마 - 시장이 아직 못 따라잡았을 가능성.",
  "Early Buzz": "뉴스가 급증했지만 실적은 아직 안 나온 테마.",
  "Full Alignment": "뉴스·실적·주가가 다 같은 방향으로 움직이는 테마.",
  "Overheated Buzz": "뉴스·주가는 뜨거운데 실적은 뒤처진 테마.",
  "Full Decline": "세 축 다 하락한 테마.",
};

function arrowGlyph(a: Arrow): string {
  if (a === "up2") return "↑↑";
  if (a === "up1") return "↑";
  if (a === "flat") return "→";
  if (a === "down") return "↓";
  return "–";
}
function arrowColors(a: Arrow): { fg: string; bg: string } {
  if (a === "up2" || a === "up1") return { fg: GOOD, bg: GOOD_SOFT };
  if (a === "down") return { fg: DANGER, bg: DANGER_SOFT };
  if (a === "flat") return { fg: MUTED, bg: MUTED_SOFT };
  return { fg: FAINT, bg: "transparent" };
}
function pct(n: number | null, digits = 1): string {
  if (n == null) return "-";
  const v = (n * 100).toFixed(digits);
  return `${n >= 0 ? "+" : ""}${v}%`;
}
function isMoving(a: Arrow): boolean {
  return a === "up2" || a === "up1" || a === "down";
}

function ArrowChip({ axis, arrow }: { axis: string; arrow: Arrow }) {
  const { fg, bg } = arrowColors(arrow);
  return (
    <div className="flex w-14 shrink-0 flex-col items-center gap-0.5 rounded-lg py-1.5" style={{ background: bg }}>
      <span className="text-[11px]" style={{ color: MUTED }}>{axis}</span>
      <span className="text-[17px] font-bold" style={{ color: fg, fontFamily: MONO }}>{arrowGlyph(arrow)}</span>
    </div>
  );
}

function LabelBadge({ label }: { label: string }) {
  return (
    <span
      className="ml-auto shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-[13px] font-extrabold"
      style={BADGE_STYLE[label] ?? { background: ACCENT_SOFT, color: ACCENT }}
      title={LABEL_NOTE[label] ?? label}
    >
      {label}{LABEL_KO[label] && <span className="ml-1 font-semibold opacity-80">· {LABEL_KO[label]}</span>}
    </span>
  );
}

/** 발견 단계 표시(●─○─○) - 지금 보는 게 몇 번째 단계인지. */
function StageRail({ index, color }: { index: number; color: string }) {
  return (
    <div className="mb-2.5 flex items-center gap-1.5">
      {[0, 1, 2].map((i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <span className="h-px w-6" style={{ background: "var(--border-ctrl)" }} />}
          <span
            className="h-[7px] w-[7px] rounded-full"
            style={
              i === index
                ? { background: color, boxShadow: index === 0 ? `0 0 7px ${color}` : "none" }
                : { background: "var(--border-ctrl)" }
            }
          />
        </span>
      ))}
    </div>
  );
}

const LINKAGE_STYLE: Record<string, { label: string; fg: string; bg: string }> = {
  direct: { label: "주력", fg: "#4ade80", bg: "rgba(74,222,128,0.14)" },
  partial: { label: "일부", fg: "#6fb3b8", bg: "rgba(111,179,184,0.14)" },
  peripheral: { label: "간접", fg: FAINT, bg: "transparent" },
  perceived: { label: "시장 인식", fg: "#d4a95a", bg: "transparent" },
};
function LinkageBadge({ linkage }: { linkage: string }) {
  const s = LINKAGE_STYLE[linkage] ?? { label: linkage, fg: MUTED, bg: "transparent" };
  return (
    <span
      className="whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
      style={{ background: s.bg, color: s.fg, border: s.bg === "transparent" ? "1px solid var(--border)" : "none" }}
    >
      {s.label}
    </span>
  );
}

// 탈락 사유 문자열("ROE 5.0% (<8%)")을 배지에 넣을 짧은 말로 줄인다.
function shortReason(flag: string): string {
  if (flag.startsWith("Piotroski")) return "F-Score";
  if (flag.startsWith("ROE")) return "ROE";
  if (flag.startsWith("부채비율")) return "부채";
  if (flag.startsWith("이자보상")) return "이자보상";
  if (flag.includes("현금흐름")) return "현금흐름";
  if (flag.includes("감소")) return "매출감소";
  return flag.split(" ")[0];
}

function FinanceBadge({ finance }: { finance: Member["finance"] }) {
  const base = "whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px]";

  if (finance.status === "pass") {
    return (
      <span className={`${base} font-semibold`} style={{ background: GOOD_SOFT, color: GOOD }}>
        재무 통과{finance.piotroski != null && ` (F${finance.piotroski})`}
      </span>
    );
  }

  if (finance.status === "fail") {
    // 사유를 다 붙이면 표가 넘치므로 앞 2개만 - 전체는 title로 볼 수 있게.
    const rs = finance.reasons ?? [];
    const shown = Array.from(new Set(rs.map(shortReason))).slice(0, 2);
    return (
      <span className={`${base} font-semibold`} style={{ background: DANGER_SOFT, color: DANGER }}
            title={rs.join(" / ")}>
        재무 탈락{shown.length > 0 && ` (${shown.join("·")})`}
      </span>
    );
  }

  if (finance.status === "insufficient") {
    return (
      <span className={base} style={{ background: MUTED_SOFT, color: MUTED }}>
        데이터 부족
      </span>
    );
  }

  // 스크리닝 결과 자체가 없는 종목 - 유니버스 밖이거나 아직 한 번도 안 돌았음.
  // 이때만 "미확인"이며, 탈락으로 단정하지 않는다(3분류 원칙).
  return (
    <span className={base} style={{ color: FAINT, border: "1px solid var(--border)" }}>
      미확인
    </span>
  );
}

function MembersTable({ members, loading, market }: { members: Member[]; loading: boolean; market: string }) {
  if (loading) return <div className="py-4 text-[12px]" style={{ color: MUTED }}>불러오는 중...</div>;
  if (members.length === 0) return <div className="py-4 text-[12px]" style={{ color: MUTED }}>소속 기업 정보를 찾을 수 없습니다.</div>;

  return (
    <div className="overflow-x-auto rounded-lg" style={{ border: "1px solid var(--border)" }}>
      <table className="w-full text-[13px]" style={{ borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "var(--bg-inset)" }}>
            {[market === "KR" ? "종목" : "티커", "가치사슬 단계", "근거", "구분", "재무"].map((h) => (
              <th key={h} className="whitespace-nowrap px-3 py-2 text-left text-[12px] font-bold" style={{ color: MUTED, borderBottom: "1px solid var(--border)" }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.ticker} style={{ borderBottom: "1px solid var(--border)" }}>
              <td className="px-3 py-2 align-top">
                {market === "KR" ? (
                  // 한국 종목코드(6자리 숫자)는 사람이 못 읽으니 회사명을 앞세우고
                  // 코드는 보조로 작게 - 미국은 티커 자체가 식별자라 그대로 둔다.
                  <div className="flex flex-col">
                    <StockLink market="KR" symbol={m.ticker} className="whitespace-nowrap font-bold" style={{ color: "var(--text-primary)" }}>
                      {krStockName(m.ticker)}
                    </StockLink>
                    <span className="text-[11px]" style={{ fontFamily: MONO, color: FAINT }}>{m.ticker}</span>
                  </div>
                ) : (
                  <StockLink market="US" symbol={m.ticker} className="font-bold" style={{ fontFamily: MONO, color: "var(--num)" }}>{m.ticker}</StockLink>
                )}
              </td>
              <td className="px-3 py-2 align-top">
                <div className="flex flex-wrap gap-1">
                  {m.stage && (
                    <span className="whitespace-nowrap rounded-full px-2 py-0.5 text-[11px]" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)", color: MUTED }}>
                      {m.stage}
                    </span>
                  )}
                  {m.other_themes.map((t) => (
                    <span key={t} className="whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold" style={{ background: ACCENT_SOFT, color: ACCENT }}>
                      {themeName(t).ko}에도 소속
                    </span>
                  ))}
                  {(m.other_perceived ?? []).map((t) => (
                    <span key={`p-${t}`} className="whitespace-nowrap rounded-full px-2 py-0.5 text-[11px]"
                      style={{ color: LINKAGE_STYLE.perceived.fg, border: "1px dashed var(--border)" }}
                      title="사업 소속이 아니라 테마 ETF 편입 근거 - 테마 신호 계산에는 들어가지 않는다">
                      {themeName(t).ko} 시장 인식
                    </span>
                  ))}
                </div>
              </td>
              <td className="max-w-[560px] px-3 py-2 align-top text-[12.5px]" style={{ color: MUTED }}>{m.evidence ?? "-"}</td>
              <td className="px-3 py-2 align-top">
                <LinkageBadge linkage={m.linkage} />
              </td>
              <td className="px-3 py-2 align-top">
                <FinanceBadge finance={m.finance} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NewsList({ articles, loading }: { articles: Article[]; loading: boolean }) {
  if (loading) return <div className="py-3 text-[12px]" style={{ color: MUTED }}>불러오는 중...</div>;
  if (articles.length === 0) return <div className="py-3 text-[12px]" style={{ color: MUTED }}>이번 주 수집된 기사가 없습니다.</div>;
  return (
    <ul className="flex flex-col gap-1.5">
      {articles.map((a, i) => (
        <li key={i} className="text-[12.5px]">
          <a href={a.url} target="_blank" rel="noopener noreferrer" className="hover:underline" style={{ color: "var(--text-secondary)" }}>
            {a.title}
          </a>
          <span className="ml-1.5" style={{ color: FAINT }}>
            {a.source ?? ""}{a.published_at ? ` · ${a.published_at}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

function ThemeCard({ signal, market, compact = false, ev }:
  { signal: ThemeSignal; market: string; compact?: boolean; ev?: ThemeEvents }) {
  const [open, setOpen] = useState(false);
  const [members, setMembers] = useState<Member[] | null>(null);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [showNews, setShowNews] = useState(false);
  const [articles, setArticles] = useState<Article[] | null>(null);
  const [loadingNews, setLoadingNews] = useState(false);
  const { ko, en } = themeName(signal.theme_id);

  const toggle = useCallback(() => {
    setOpen((o) => !o);
    if (!members && !loadingMembers) {
      setLoadingMembers(true);
      fetch(`/api/radar/members?theme_id=${encodeURIComponent(signal.theme_id)}&market=${market}`)
        .then((r) => r.json())
        .then((d) => setMembers(d.members ?? []))
        .catch(() => setMembers([]))
        .finally(() => setLoadingMembers(false));
    }
  }, [members, loadingMembers, signal.theme_id, market]);

  const toggleNews = useCallback(() => {
    setShowNews((s) => !s);
    if (!articles && !loadingNews) {
      setLoadingNews(true);
      fetch(`/api/radar/news?theme_id=${encodeURIComponent(signal.theme_id)}&market=${market}`)
        .then((r) => r.json())
        .then((d) => setArticles(d.articles ?? []))
        .catch(() => setArticles([]))
        .finally(() => setLoadingNews(false));
    }
  }, [articles, loadingNews, signal.theme_id, market]);

  return (
    <div
      className={compact ? "overflow-hidden" : "mb-3 overflow-hidden rounded-2xl"}
      style={
        compact
          ? { borderBottom: "1px solid var(--border-dim)" }
          : { background: "var(--bg-card)", border: "1px solid var(--border)" }
      }
    >
      <button
        onClick={toggle}
        className={compact
          ? "flex w-full flex-wrap items-center gap-3 px-3 py-2 text-left"
          : "flex w-full flex-wrap items-center gap-4 px-4 py-3.5 text-left"}
        style={{ cursor: "pointer" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-raised)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      >
        {compact ? (
          // 조밀 모드 - 라벨 없는 테마가 많을 때 표처럼 훑을 수 있게. 다만
          // 표로 만들지 않고 버튼을 유지해서, 펼쳐서 소속 기업·기사를 보는
          // 기능은 그대로 남긴다.
          <>
            <span className="min-w-[150px] shrink-0 text-[13.5px] font-semibold" style={{ color: "var(--text-primary)" }}>{ko}</span>
            <span className="flex gap-3" style={{ fontFamily: MONO }}>
              {([["뉴스", signal.news_arrow], ["실적", signal.earn_arrow], ["주가", signal.price_arrow]] as const).map(([ax, ar]) => (
                <span key={ax} className="flex items-baseline gap-1 text-[12px]" style={{ color: FAINT }}>
                  {ax}
                  <b className="text-[14px]" style={{ color: arrowColors(ar).fg }}>{arrowGlyph(ar)}</b>
                </span>
              ))}
            </span>
          </>
        ) : (
          <>
            <div className="flex min-w-[170px] shrink-0 flex-col gap-0.5">
              <span className="text-[16px] font-bold" style={{ color: "var(--text-primary)" }}>{ko}</span>
              <span className="text-[12px]" style={{ color: FAINT }}>{en}</span>
            </div>
            <div className="flex gap-2.5">
              <ArrowChip axis="뉴스" arrow={signal.news_arrow} />
              <ArrowChip axis="실적" arrow={signal.earn_arrow} />
              <ArrowChip axis="주가" arrow={signal.price_arrow} />
            </div>
          </>
        )}
        {signal.label && <LabelBadge label={signal.label} />}
        <EventChip ev={ev} />
        <span className="ml-auto shrink-0 text-[13px] transition-transform" style={{ color: FAINT, transform: open ? "rotate(90deg)" : "none" }}>▸</span>
      </button>

      {open && (
        <div className="px-4 pb-4" style={{ borderTop: "1px solid var(--border)" }}>
          <div className="mt-3 flex justify-end">
            <Link href={`/radar/theme?id=${encodeURIComponent(signal.theme_id)}&market=${market}`}
              className="text-[12px] font-semibold" style={{ color: ACCENT }}>
              흐름 이력 보기 →
            </Link>
          </div>
          <div className="my-3 grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
            <div className="rounded-lg px-3 py-2 text-[13px]" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)", color: MUTED }}>
              {signal.earn_arrow === "na" ? (
                <>
                  실적 판정 보류(표본 부족)
                  {signal.earn_members != null && (
                    <span className="ml-1 text-[11px]" style={{ color: FAINT }}>
                      {signal.earn_members}개사 중 {signal.earn_improved}개 확인
                    </span>
                  )}
                </>
              ) : signal.earn_members != null ? (
                <>
                  <b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>
                    {signal.earn_members}개사 중 {signal.earn_improved}개
                  </b> 매출 성장률이 시장 중앙값 초과
                  {signal.earn_as_of && <span className="ml-1 text-[11px]" style={{ color: FAINT }}>{signal.earn_as_of} 기준</span>}
                  {signal.earn_surprise_n != null && signal.earn_surprise_n > 0 && (
                    <div className="mt-1 text-[12px]" style={{ color: MUTED }}>
                      최근 발표 <b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>
                        {signal.earn_surprise_n}개사 중 {signal.earn_surprise_beat}개
                      </b> 추정치 상회
                      {signal.earn_surprise_median != null && (
                        <> · 서프라이즈 중앙값 <b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>
                          {signal.earn_surprise_median > 0 ? "+" : ""}{signal.earn_surprise_median.toFixed(1)}%
                        </b></>
                      )}
                    </div>
                  )}
                </>
              ) : "실적 데이터 없음"}
            </div>
            <div className="rounded-lg px-3 py-2 text-[13px]" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)", color: MUTED }}>
              뉴스 이번 주 <b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>{signal.news_count ?? "-"}건</b>
              {" / "}8주 중앙값 <b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>{signal.news_baseline != null ? Math.round(signal.news_baseline) : "-"}건</b>
            </div>
            <div className="rounded-lg px-3 py-2 text-[13px]" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)", color: MUTED }}>
              주가 중앙값 <b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>{pct(signal.price_median_ret)}</b>
              {signal.price_excess != null && <> · 지수 대비 <b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>{pct(signal.price_excess)}p</b></>}
              {signal.price_volume_ratio != null && (
                <> · 거래대금 <b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>
                  x{signal.price_volume_ratio.toFixed(2)}
                </b> <span className="text-[11px]" style={{ color: FAINT }}>(직전 4주 대비)</span></>
              )}
            </div>
          </div>
          <MembersTable members={members ?? []} loading={loadingMembers} market={market} />
          <EventList ev={ev} market={market} />

          <button
            onClick={toggleNews}
            className="mt-3 rounded-lg px-3 py-1.5 text-[12px] font-semibold"
            style={{ border: "1px solid var(--border)", color: showNews ? ACCENT : MUTED, background: showNews ? ACCENT_SOFT : "transparent" }}
          >
            기사 보기{showNews ? " ▴" : " ▾"}
          </button>
          {showNews && (
            <div className="mt-2 rounded-lg px-3 py-2" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
              <NewsList articles={articles ?? []} loading={loadingNews} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// 단계 섹션 접기 상태를 기억해 둔다 - 이 브라우저에서 마지막으로 접어둔 상태
// 그대로 다음에 열린다. 서버에 저장하지 않는다(보는 사람마다 취향이 다를 뿐
// 데이터가 아니다). 접근 실패(프라이빗 모드 등)해도 화면은 정상 동작해야 하므로
// 모두 try/catch로 감싼다.
const STAGE_COLLAPSE_KEY = "radar_collapsed_stages";

function loadCollapsedStages(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(STAGE_COLLAPSE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveCollapsedStages(v: Record<string, boolean>): void {
  try {
    localStorage.setItem(STAGE_COLLAPSE_KEY, JSON.stringify(v));
  } catch {
    // 저장 실패해도 이번 화면에서는 그대로 접고 펼 수 있다 - 다음 방문에서만 기억을 못 한다.
  }
}

export default function RadarPage() {
  const { market } = useMarket();
  const [weekStart, setWeekStart] = useState<string | null>(null);
  const [signals, setSignals] = useState<ThemeSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [collapsedStages, setCollapsedStages] = useState<Record<string, boolean>>({});
  const [events, setEvents] = useState<Record<string, ThemeEvents>>({});

  useEffect(() => {
    setCollapsedStages(loadCollapsedStages());
  }, []);

  const toggleStage = (key: string) => {
    setCollapsedStages((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      saveCollapsedStages(next);
      return next;
    });
  };

  useEffect(() => {
    setLoading(true);
    fetch(`/api/radar?market=${market}`)
      .then((r) => r.json())
      .then((d) => {
        setWeekStart(d.week_start ?? null);
        setSignals(d.signals ?? []);
      })
      .catch(() => { setWeekStart(null); setSignals([]); })
      .finally(() => setLoading(false));
    fetch(`/api/radar/events?market=${market}`)
      .then((r) => r.json())
      .then((d) => setEvents(d.themes ?? {}))
      .catch(() => setEvents({}));
  }, [market]);

  const anyMoving = (s: ThemeSignal) =>
    isMoving(s.news_arrow) || isMoving(s.earn_arrow) || isMoving(s.price_arrow);

  const labeled = signals.filter((s) => s.label);
  const unlabeledMoving = signals.filter((s) => !s.label && anyMoving(s));
  const movingCount = signals.filter(anyMoving).length;
  const quietCount = signals.length - movingCount;
  // 세 축이 다 조용한데 최근 7일 소속 기업 공시·내부자 매수가 있는 테마 - 실적 축보다 먼저 나오는 신호라 따로 보인다.
  // 순서는 이벤트가 있었던 소속 기업 수(공시 원문 건수 그대로) - 점수가 아니다.
  // 주별 변화가 있으면(2026-10-21부터) "평소보다 많음"인 테마만 - 공시가 원래 흔한 테마가 늘 걸리지 않게. 예전 계산값이면 최근 7일 이벤트 유무로.
  const hasWeekly = Object.values(events).some((e) => !!e.counts.weekly);
  const quietWithEvents = signals.filter((s) => !anyMoving(s) && (hasWeekly ? isBusier(events[s.theme_id]) : hasRecent(events[s.theme_id])))
    .sort((a, b) => quietOrder(events[b.theme_id]) - quietOrder(events[a.theme_id]));

  // 단계별로 묶되, 라벨 순서는 STAGES 정의 순서를 따른다.
  const stageGroups = STAGES.map((stage) => ({
    stage,
    items: (stage.labels as readonly string[]).flatMap((label) =>
      labeled.filter((s) => s.label === label)
    ),
  }));

  // 폭: 896px(max-w-4xl)에서 다른 화면과 같은 1280px로(2026-10-04). 설명 문단은 읽기 좋게 ch 단위 폭을 유지한다.
  return (
    <div className="mx-auto max-w-[1280px]" style={{ color: "var(--text-primary)" }}>
      <PageHeader title="이번 주 움직인 테마"
        asOf={!loading && <AsOf date={weekStart} cadence="매주 월요일 아침" staleDays={14} />}
        desc="종합 점수도, 매수 추천도 없습니다. 뉴스·실적·주가 세 축을 각각 보여주고, 정해진 조합에만 이름을 붙입니다 — 나머지는 화살표로만 남겨둡니다." />

      {/* 라벨이 적은 게 "빈 화면"이 아니라 "걸러낸 결과"로 읽히도록 깔때기로 보여준다. */}
      {!loading && signals.length > 0 && (
        <>
          <div className="mt-4 flex overflow-hidden rounded-xl" style={{ border: "1px solid var(--border)", background: "var(--bg-card)" }}>
            {[
              { n: signals.length, k: "관찰한 테마", on: false },
              { n: movingCount, k: "축이 하나라도 움직임", on: false },
              { n: labeled.length, k: "6개 조합에 해당", on: true },
            ].map((step, i) => (
              <div key={step.k} className="flex-1 px-4 py-2.5"
                   style={{ borderRight: i < 2 ? "1px solid var(--border-dim)" : "none",
                            background: step.on ? "var(--bg-raised)" : "transparent" }}>
                <div className="text-[21px] font-extrabold" style={{ fontFamily: MONO, color: step.on ? ACCENT : "var(--text-primary)" }}>{step.n}</div>
                <div className="text-[11.5px]" style={{ color: MUTED }}>{step.k}</div>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[12px]" style={{ color: FAINT }}>
            기준 주 {weekStart} · {market === "KR" ? "한국" : "미국"} 시장 · 조합에 안 맞으면 억지로 이름 붙이지 않습니다 — 적게 나오는 것이 정상입니다.
          </p>
        </>
      )}

      <div className="mt-5 flex flex-wrap gap-4 rounded-xl px-4 py-3 text-[12px]" style={{ background: "var(--bg-inset)", border: "1px solid var(--border)", color: MUTED }}>
        <span><b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>↑↑</b> 강함</span>
        <span><b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>↑</b> 상승</span>
        <span><b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>→</b> 보합</span>
        <span><b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>↓</b> 하락</span>
        <span><b style={{ fontFamily: MONO, color: "var(--text-primary)" }}>–</b> 표본 부족</span>
        {/* 오늘 실적 축이 "중앙값 대비"로 바뀌어서, 각 축의 비교 대상을 명시하는 게 중요해졌다. */}
        <span style={{ color: FAINT }}>뉴스=직전 4주 대비 · 실적=시장 중앙값 대비 · 주가=지수 대비</span>
      </div>

      <div className="mt-2 mb-6 flex flex-wrap items-center gap-2.5 rounded-xl px-4 py-3 text-[11.5px]"
           style={{ background: "var(--bg-inset)", border: "1px solid var(--border)", color: FAINT }}>
        <span>배지 강도 =</span>
        {["Quiet Strength", "Quiet Recovery", "Early Buzz", "Full Alignment"].map((l) => (
          <span key={l} className="whitespace-nowrap rounded-full px-2.5 py-1 text-[11.5px] font-extrabold"
                style={BADGE_STYLE[l]} title={LABEL_NOTE[l]}>{labelWithKo(l)}</span>
        ))}
        <span>← 이른 신호일수록 강하게. 카드 모양은 전부 동일합니다.</span>
      </div>

      {loading ? (
        <div className="py-16 text-center text-[13px]" style={{ color: MUTED }}>불러오는 중...</div>
      ) : signals.length === 0 ? (
        <EmptyState title="아직 계산된 테마 신호가 없습니다" hint="매주 월요일 아침(일요일 밤 실행) 뉴스·실적·주가를 계산한 뒤 표시됩니다." />
      ) : (
        <>
          {/* 발견 단계 3섹션 - 해당 없는 단계도 숨기지 않는다(헤더+개수는 항상 보인다).
              "이번 주는 이 단계가 비었다"는 것 자체가 정보라서 완전히 없애지는
              않되, 본문(설명·카드·해당없음 안내)은 기본으로 접어 둔다 - 세 섹션이
              전부 비어있는 주에는 빈 칸 3개가 화면을 다 차지했었다. 펼쳐서 본 뒤엔
              그 선택을 기억해 다음 방문에서도 펼쳐진 채로 보여준다(collapsedStages에
              값이 없을 때만 기본 접힘 - false를 저장해 뒀으면 펼친 채 유지).*/}
          {stageGroups.map(({ stage, items }, i) => {
            const collapsed = collapsedStages[stage.key] ?? true;
            return (
              <div key={stage.key} className="mt-8">
                <StageRail index={i} color={stage.color} />
                <button
                  type="button"
                  onClick={() => toggleStage(stage.key)}
                  className="mb-1 flex w-full items-center gap-2 text-left"
                  style={{ background: "transparent", border: "none", padding: 0, cursor: "pointer" }}
                  aria-expanded={!collapsed}
                >
                  {collapsed
                    ? <ChevronRight size={15} style={{ color: MUTED, flexShrink: 0 }} />
                    : <ChevronDown size={15} style={{ color: MUTED, flexShrink: 0 }} />}
                  <span className="flex flex-wrap items-baseline gap-2.5">
                    <h2 className="text-[16.5px] font-extrabold" style={{ color: stage.color }}>{stage.name}</h2>
                    <span className="text-[11.5px]" style={{ color: FAINT, fontFamily: MONO }}>{stage.when}</span>
                    <span className="text-[11.5px] font-semibold" style={{ color: items.length > 0 ? stage.color : FAINT, fontFamily: MONO }}>
                      {items.length > 0 ? `${items.length}개` : "해당 없음"}
                    </span>
                  </span>
                </button>
                {!collapsed && (
                  <>
                    <p className="mb-3 max-w-[70ch] text-[12.5px]" style={{ color: MUTED }}>{stage.desc}</p>
                    {items.length > 0 ? (
                      items.map((s) => <ThemeCard key={s.theme_id} signal={s} market={market} ev={events[s.theme_id]} />)
                    ) : (
                      <div className="rounded-xl px-4 py-3 text-[12.5px]"
                           style={{ border: "1px dashed var(--border-ctrl)", background: "var(--bg-inset)", color: MUTED }}>
                        이번 주 해당 없음 — {(stage.labels as readonly string[]).join(" · ")} 조합에 맞는 테마가 없었습니다.
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          })}

          {unlabeledMoving.length > 0 && (
            <div className="mt-10">
              <div className="mb-1 flex items-baseline gap-2.5">
                <h2 className="text-[15px] font-bold">라벨 없음 — 화살표만</h2>
                <span className="text-[12px]" style={{ color: FAINT, fontFamily: MONO }}>{unlabeledMoving.length}개</span>
              </div>
              <p className="mb-3 max-w-[68ch] text-[12.5px]" style={{ color: MUTED }}>
                6개 조합에 안 맞는 테마입니다. 판단은 직접 — 눌러서 소속 기업·기사를 볼 수 있습니다.
              </p>
              <div className="overflow-hidden rounded-xl" style={{ border: "1px solid var(--border)", background: "var(--bg-card)" }}>
                {unlabeledMoving.map((s) => (
                  <ThemeCard key={s.theme_id} signal={s} market={market} compact ev={events[s.theme_id]} />
                ))}
              </div>
            </div>
          )}

          {quietWithEvents.length > 0 && (
            <div className="mt-10">
              <div className="mb-1 flex items-baseline gap-2.5">
                <h2 className="text-[15px] font-bold">{hasWeekly ? "축은 조용, 소속 기업 공시는 평소보다 많음" : "축은 조용, 소속 기업 공시는 있음"}</h2>
                <span className="text-[12px]" style={{ color: FAINT, fontFamily: MONO }}>{quietWithEvents.length}개</span>
              </div>
              <p className="mb-3 max-w-[68ch] text-[12.5px]" style={{ color: MUTED }}>
                {hasWeekly
                  ? "뉴스·실적·주가는 움직이지 않았지만 최근 7일 소속 기업 공시(공급계약·중요 계약 등)나 내부자 장내 매수가 그 테마의 평소(직전 4주 주당 평균)의 2배 이상인 테마입니다(공시 3건·내부자 2개사 이상일 때만). "
                  : "뉴스·실적·주가는 움직이지 않았지만 최근 7일 소속 기업에 공급계약·중요 계약·내부자 장내 매수 같은 공시가 있었던 테마입니다. "}
                실적 축은 분기 공시가 나와야 움직여서, 계약·내부자 매수가 먼저 보일 수 있습니다 — 눌러서 공시 목록을 보세요.
              </p>
              <div className="overflow-hidden rounded-xl" style={{ border: "1px solid var(--border)", background: "var(--bg-card)" }}>
                {quietWithEvents.map((s) => (
                  <ThemeCard key={s.theme_id} signal={s} market={market} compact ev={events[s.theme_id]} />
                ))}
              </div>
            </div>
          )}

          {quietCount > 0 && (
            <div className="mt-3 rounded-xl px-4 py-3 text-[12.5px]"
                 style={{ border: "1px dashed var(--border-ctrl)", background: "var(--bg-inset)", color: MUTED }}>
              조용한 테마 <b style={{ fontFamily: MONO, color: "var(--text-secondary)" }}>{quietCount}개</b>
              {" "}— 세 축 모두 움직임이 없어 표시하지 않았습니다{quietWithEvents.length > 0 ? ` (그중 ${hasWeekly ? "공시가 평소보다 많았던" : "공시가 있었던"} ${quietWithEvents.length}개는 위에)` : ""}.
            </div>
          )}
        </>
      )}

      <div className="mt-12 border-t pt-5 text-[12px] leading-relaxed" style={{ borderColor: "var(--border)", color: FAINT }}>
        <p>이 화면이 하지 않는 것</p>
        <ul className="mt-1 list-disc pl-5">
          <li>종합 점수·등급 표시</li>
          <li>&ldquo;매수 추천&rdquo; / &ldquo;BUY&rdquo; / &ldquo;우선순위&rdquo; 류의 표현</li>
          <li>테마를 수익률 기대치로 정렬</li>
        </ul>
      </div>
    </div>
  );
}
