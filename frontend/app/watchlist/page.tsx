"use client";

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { externalQuoteUrl } from "@/src/components/StockLink";
import { X, Info, Pencil, Search } from "lucide-react";
import StockTechPanel from "@/src/components/StockTechPanel";
import { themeName } from "@/src/lib/themeNames";
import { ObservationForm } from "@/src/components/Observation";
import { TagBadges } from "@/src/components/TagBadge";
import AsOf from "@/src/components/AsOf";
import { labelWithKo } from "@/src/lib/labelNames";

interface Candidate {
  market: string;
  symbol: string;
  name: string | null;
  market_cap: number | null;
  sector: string | null;
  piotroski: number | null;
  debt_ratio: number | null;
  interest_coverage: number | null;
  cfo_positive_count: number;
  red_flags: string[];
  regime_fit: "growth" | "dividend" | "neutral";
  roe: number | null;
  current_price: number | null;
  // 밸류 지표. 이 목록의 다른 지표는 전부 "튼튼한가"를 보는데, 이 둘만 "싼가"를 본다.
  // 4분기 중 한 분기라도 비면 null, PER은 적자면 null(원칙 4 - 계산 불가는 탈락이 아니다).
  psr?: number | null;
  per?: number | null;
  valuation_tier?: string | null;   // 싼 편 / 중간 / 비싼 편. 같은 시장 후보 안에서 3등분
  // 성장 지표. 밸류와 달리 절대 기준(0%, 10%)으로 나눈다 - 후보 대부분이 이미
  // 성장 중이라 순위로 나누면 +3% 성장 기업에 "역성장" 라벨이 붙는다(SPEC_watchlist_growth.md).
  revenue_cagr_3y?: number | null;
  revenue_yoy?: number | null;
  op_margin_direction?: "개선" | "악화" | null;
  // 분기 영업이익률 - 최근 분기 vs 1년 전 같은 분기(2026-10-05). 연간 3년 비교보다 이른 신호, ±1%p 경계.
  op_margin_q_now?: number | null;
  op_margin_q_change?: number | null;
  op_margin_q_status?: "개선" | "악화" | "유지" | null;
  // 최근 분기 매출 전년동기 대비(2026-10-09) - 3년 판정(growth_tier)과 따로 보여 주는 "지금 흐름". 같은 0%/10% 경계.
  rev_q_yoy?: number | null;
  rev_q_tier?: string | null;
  rev_q_quarter?: string | null;
  // 최근 4개 분기 합 대 직전 4개 분기 합(2026-10-09) - 연속 8분기가 있을 때만(지금은 한국 DART 종목)
  rev_ttm_yoy?: number | null;
  rev_ttm_tier?: string | null;
  // FCF 수익률(2026-10-19) - 3년 평균 FCF / 시가총액. 상세 카드 전용, 등급 없음
  fcf_yield_3y?: number | null;
  fcf_yield_latest?: number | null;
  fcf_negative_years?: number | null;
  fcf_latest_year?: string | null;
  rev_ttm_quarter?: string | null;
  // 최근 100일 안 실적 발표의 EPS 서프라이즈(2026-10-05, earnings_surprise)
  surprise?: { pct: number; date: string; estimate: number | null; reported: number | null } | null;
  // yfinance 기업 정보에서 꺼낸 사실 값(수집 시점 기준) - 애널리스트 수, 52주 고점·저점 대비
  facts?: { analysts: number | null; from_high: number | null; from_low: number | null; as_of: string | null } | null;
  growth_tier?: string | null;   // 성장 / 정체 / 역성장
  // 유니버스 출처. 미국만 값이 있고("sp500"/"sp400") 한국은 null이다.
  // 표에는 넣지 않는다 - 종목을 고를 때 쓰는 정보가 아니라 "이 후보가 어디서
  // 왔나"를 나중에 검증하려고 남기는 태그다(SPEC_us_universe_sp400.md 3장).
  universe_source?: string | null;
  data_notes?: { interest?: string; debt?: string };
  // 직전 스크리닝 회차에 없던 종목(= 이번에 새로 필터를 통과). 직전 회차 자체가
  // 없으면(첫 스크리닝) true가 아니라 null - 모르는 걸 "신규"로 단정하지 않는다.
  is_new?: boolean | null;
  first_seen?: string | null;   // 이력상 처음 후보가 된 날
  is_reentry?: boolean;         // 예전에 후보였다가 빠진 뒤 다시 들어온 것
  // 사업 소속(direct/partial) 테마와 그 테마의 이번 주 레이더 라벨·최근 분기 분류(2026-10-04)
  themes?: { theme_id: string; label: string | null; quarterly: string | null; earn_arrow?: string | null; price_arrow?: string | null }[];
}

// "테마 흐름과 겹침"의 기준: 펀더멘털이 먼저 움직인 테마. 레이더 Quiet 단계 라벨이거나
// 분기 분류가 "조용한 변화". Buzz·Full은 이미 알려졌거나 기대만 앞선 구간이라 넣지 않는다.
const FLOW_LABELS = new Set(["Quiet Strength", "Quiet Recovery"]);
// 금융업 판정 - src/analyzers/trap_filter.py FINANCIAL_SECTORS와 같은 목록(FCF 수익률을 계산하지 않는 업종)
const FINANCIAL_SECTORS = ["Financial Services", "Banking", "Insurance", "금융", "은행", "보험"];
const isFinancialSector = (sector: string | null | undefined) =>
  FINANCIAL_SECTORS.some((s) => (sector ?? "").includes(s));
// 시장 인식 소속 표시색 - 테마 레이더의 LINKAGE_STYLE.perceived와 같은 색
const PERCEIVED_FG = "#d4a95a";
type ThemeRef = { label: string | null; quarterly: string | null; earn_arrow?: string | null; price_arrow?: string | null };
const isFlowTheme = (t: ThemeRef) =>
  (t.label != null && FLOW_LABELS.has(t.label)) || t.quarterly === "조용한 변화";
// 라벨이 하나도 없는 동안(뉴스 기준선 4주 쌓이는 중)의 대체 기준: 실적 ↑인데 주가는 ↑ 아님(→·↓).
// Quiet 라벨의 실적·주가 조건과 같고 뉴스 조건만 빠진 것 - 뉴스를 못 보는 동안 임시로 쓴다(2026-10-05 사용자 결정).
const arrowText = (a?: string | null) =>
  a === "up2" ? "↑↑" : a === "up1" ? "↑" : a === "flat" ? "→" : a === "down" ? "↓" : "–";
const isInterimFlow = (t: ThemeRef) =>
  (t.earn_arrow === "up1" || t.earn_arrow === "up2") && (t.price_arrow === "flat" || t.price_arrow === "down");

// 조합 보기 - 기존 토글 여러 개를 한 번에 거는 지름길. 순위가 아니라 "이 조합만" 보는 것.
type PresetKey = "cheap_growth" | "new_growth" | "cheap_decline" | "turnaround";
// 실적 반전(2026-10-17): 3년 판정은 정체·역성장인데 지금 흐름은 성장. 지금 흐름은 최근 4개 분기 합 비교("1년")가 있으면 그것,
// 없으면(지금 미국 전부 - 분기 데이터 5개) 최근 분기 전년동기 비교로 대신한다. 세 판정을 합친 점수가 아니라 두 판정의 조합만 본다.
const isTurnaround = (c: Candidate) =>
  (c.growth_tier === "정체" || c.growth_tier === "역성장") &&
  (c.rev_ttm_tier != null ? c.rev_ttm_tier === "성장" : c.rev_q_tier === "성장");
const PRESETS: { key: PresetKey; label: string; note: string; test: (c: Candidate) => boolean }[] = [
  { key: "cheap_growth", label: "싸면서 성장", note: "밸류 싼 편 + 매출 3년 성장",
    test: (c) => c.valuation_tier === "싼 편" && c.growth_tier === "성장" },
  { key: "new_growth", label: "이번 주 신규 + 성장", note: "이번 회차에 처음 통과 + 매출 3년 성장",
    test: (c) => c.is_new === true && c.growth_tier === "성장" },
  { key: "turnaround", label: "실적 반전",
    note: "매출 3년은 정체·역성장인데 최근 1년(4개 분기 합)은 성장 - 업황이 막 돌아선 종목 후보. "
        + "1년 판정이 없는 종목(지금 미국 전부)은 최근 분기 전년동기 성장으로 대신합니다(한 분기라 더 흔들림)",
    test: isTurnaround },
  { key: "cheap_decline", label: "싸지만 역성장", note: "싼 이유가 있을 수 있는 종목 - 가치 함정 점검용",
    test: (c) => c.valuation_tier === "싼 편" && c.growth_tier === "역성장" },
];

// ── 프로토타입 팔레트 (이 페이지 한정) ───────────────────────────────────────
// globals.css의 공용 토큰과는 별도로, 워치리스트 페이지에서만 새 팔레트를 시험한다.
// "터미널 앰버" — 본문은 종이빛 화이트, 티커·숫자만 앰버로 강조하는 배색.
const PAGE_BG   = "#0a0a08";
const PANEL_BG  = "#111009";  // 모달 등 주요 표면
const INSET_BG  = "#0e0d08";  // 패널 안의 중첩 카드
const INPUT_BG  = "#0d0c07";
const HOVER_BG  = "#191509";
const BORDER    = "#262112";  // 정적 카드/구분선
const BORDER_CTRL = "#453b1f"; // 체크박스·인풋 등 조작 요소 테두리

const TEXT_PRIMARY   = "#ece7d8";
const TEXT_BODY      = "#d6d0c0";
const TEXT_SECONDARY = "#a39c88";
const TEXT_MUTED     = "#8b8271"; // 공용 --text-muted와 같게(2026-10-04, 이전 #726b58)
const TEXT_FAINT     = "#736b57"; // 공용 --text-faint와 같게(2026-10-04, 이전 #423e33 - 대비 1.9:1)

const ACCENT  = "#ffb020"; // 브랜드 액센트 (오늘픽 배지·활성 탭·추가 버튼) — 시맨틱과 분리
const GOOD    = "#4ade80"; // 실제 신호색: 우수/안정/배당
const WARN    = "#facc15"; // 보통
const CAUTION = "#fb923c"; // 주의
const BAD     = "#f87171"; // 취약/위험
const INFO    = "#6fb3b8"; // 미국장/성장/COLD/필터 활성 등 보조색
const NUM     = "#e3a63e"; // 시맨틱 판단이 없는 순수 숫자(시가총액 등) · 티커 강조

const MONO = 'ui-monospace, "SF Mono", "Cascadia Code", "Roboto Mono", monospace';

// 지표가 null일 때 "-" 대신 사유 표시 (무차입=좋음, 자본잠식=주의)
const NOTE_COLOR: Record<string, string> = {
  "무차입": GOOD,
  "자본잠식(음수 자본)": CAUTION,
  "금융업 제외": TEXT_MUTED,
  "데이터 없음": TEXT_FAINT,
};
function MetricOrNote({ value, note, format }: { value: number | null; note?: string; format: (v: number) => string }) {
  if (value != null) return <span style={{ color: NUM, fontVariantNumeric: "tabular-nums" }}>{format(value)}</span>;
  if (note) return <span style={{ color: NOTE_COLOR[note] ?? TEXT_FAINT, fontSize: 11 }}>{note}</span>;
  return <span style={{ color: TEXT_FAINT }}>-</span>;
}
interface WatchItem {
  id: number;
  market: string;
  symbol: string;
  name: string | null;
  note: string | null;
  added_at: string;
  // 보유 기록. 전부 선택 입력이고, 안 적으면 그냥 관심 목록으로 쓰면 된다.
  // 수익률·순위는 만들지 않는다 - 분기 점검 때 "적어둔 조건이 현실이 됐나"만
  // 묻는 용도다(투자 실행 가이드 4단계).
  bought_at?: string | null;
  buy_price?: number | null;
  thesis_breaks?: string | null;
}
interface NarrativeBrief {
  story: string;
  catalysts: string[];
  risks: string[];
  sentiment: "HOT" | "WARM" | "COLD";
  sentiment_reason: string;
  sources: string[];
  cached_at: string;
  prev_sentiment?: "HOT" | "WARM" | "COLD" | null;
  trend?: "up" | "down" | "flat" | null;
}

// ── 지표 설명 ─────────────────────────────────────────────────────────────────
const INDICATOR_INFO = {
  fscore: {
    title: "Piotroski F-Score (0~9)",
    desc: "수익성·레버리지·운영효율 9가지 항목을 각 1점씩 채점한 재무 건전성 점수입니다.",
    levels: [
      { range: "7~9점", color: GOOD, label: "우수 — 재무 상태 탄탄" },
      { range: "5~6점", color: WARN, label: "보통 — 무난한 수준" },
      { range: "0~4점", color: BAD, label: "취약 — 스크리닝 제외" },
    ],
  },
  debt: {
    title: "부채비율 (총부채/자기자본)",
    desc: "기업이 자기자본 대비 얼마나 많은 부채를 쓰는지 나타냅니다. 낮을수록 재무가 안정적입니다. (금융업 제외)",
    levels: [
      { range: "~100%", color: GOOD, label: "안정" },
      { range: "100~150%", color: WARN, label: "보통" },
      { range: "150~200%", color: CAUTION, label: "주의" },
      { range: "200% 초과", color: BAD, label: "스크리닝 제외" },
    ],
  },
  interest: {
    title: "이자보상배율 (EBIT/이자비용)",
    desc: "영업이익으로 이자를 몇 배 낼 수 있는지 나타냅니다. 1배 미만이면 영업이익으로 이자도 못 내는 좀비기업입니다.",
    levels: [
      { range: "5x 이상", color: GOOD, label: "안전" },
      { range: "3~5x", color: WARN, label: "보통" },
      { range: "1~3x", color: CAUTION, label: "주의" },
      { range: "1x 미만", color: BAD, label: "스크리닝 제외" },
    ],
  },
  valuation: {
    title: "밸류 위치 (PSR 기준)",
    desc: "PSR은 시가총액을 최근 4분기 매출 합으로 나눈 값, PER은 순이익 합으로 나눈 값입니다. "
        + "같은 시장 후보 전체를 PSR 낮은 순으로 줄 세워 셋으로 나눈 위치를 보여줍니다. "
        + "절대적으로 싸다는 뜻이 아니라 '이 후보들 중에서' 싼 쪽이라는 뜻이고, 순위나 점수는 아닙니다. "
        + "4분기가 이어지지 않으면 '-', 적자 기업은 PER만 '-'로 둡니다.",
    levels: [
      { range: "싼 편", color: GOOD, label: "후보 중 PSR 하위 1/3" },
      { range: "중간", color: WARN, label: "가운데 1/3" },
      { range: "비싼 편", color: CAUTION, label: "후보 중 PSR 상위 1/3" },
      { range: "-", color: TEXT_FAINT, label: "분기 재무가 모자라 계산 불가" },
    ],
  },
  growth: {
    title: "성장 위치 (매출 3년 CAGR · 최근 분기)",
    desc: "연차 재무제표의 최근 4개 회계연도(정확히 3년 간격)로 매출 연평균성장률(CAGR)을 구합니다. "
        + "밸류(PSR)는 후보들 중 상대적인 순위지만, 성장은 절대 기준입니다 - 후보 대부분이 "
        + "이미 성장 중이라 순위로 나누면 +3% 성장 기업에 '역성장' 라벨이 붙기 때문입니다. "
        + "역성장이 재무 부실을 뜻하지는 않습니다 - 무차입 흑자 기업도 매출이 줄 수 있고, "
        + "함정 필터가 걸러내지 못하는 부분을 보여주는 것이 이 지표의 목적입니다. "
        + "옆의 '1년' 배지는 최근 4개 분기 매출 합을 그 전 4개 분기와, '분기' 배지는 최근 분기를 1년 전 같은 분기와 비교한 같은 경계의 판정입니다(1년이 있으면 그것을 보여 줌) - "
        + "3년 기준은 업황이 막 바뀐 기업(예: 3년 전이 직전 호황 고점)을 늦게 잡으므로 지금 흐름을 따로 보여 줍니다. "
        + "두 판정은 합치지 않고, 필터·정렬은 3년 기준을 씁니다.",
    levels: [
      { range: "성장", color: GOOD, label: "3년 CAGR(또는 분기 전년동기) 10% 이상" },
      { range: "정체", color: WARN, label: "0% ~ 10%" },
      { range: "역성장", color: CAUTION, label: "0% 미만 - 매출이 3년간 줄었다" },
      { range: "-", color: TEXT_FAINT, label: "회계기간 부족 등으로 계산 불가" },
    ],
  },
  regime: {
    title: "시장 체제 적합도",
    desc: "현재 시장 흐름(성장장/배당장)에서 이 종목이 어느 전략에 더 어울리는지를 나타냅니다.",
    levels: [
      { range: "성장", color: INFO, label: "고성장 — 매출/EPS 성장률 높음" },
      { range: "배당", color: GOOD, label: "배당 중심 — 배당수익률 2% 이상" },
      { range: "중립", color: TEXT_SECONDARY, label: "뚜렷한 특성 없음" },
    ],
  },
};

// ── Helpers ─────────────────────────────────────────────────────────────────
const FMT_CAP_US = (n: number) =>
  n >= 1e12 ? `$${(n / 1e12).toFixed(1)}T` : n >= 1e9 ? `$${(n / 1e9).toFixed(1)}B` : `$${(n / 1e6).toFixed(0)}M`;
const FMT_CAP_KR = (n: number) =>
  n >= 1e12 ? `${(n / 1e12).toFixed(1)}조` : `${(n / 1e8).toFixed(0)}억`;
function formatCap(market: string, cap: number | null) {
  if (!cap) return "-";
  return market === "KR" ? FMT_CAP_KR(cap) : FMT_CAP_US(cap);
}
function formatPrice(market: string, price: number | null) {
  if (price == null) return "-";
  return market === "KR" ? `₩${Math.round(price).toLocaleString()}` : `$${price.toFixed(2)}`;
}

function PiotroskiBadge({ score }: { score: number | null }) {
  if (score === null) return <span style={{ color: TEXT_FAINT }}>-</span>;
  const color = score >= 7 ? GOOD : score >= 5 ? WARN : BAD;
  return (
    <span style={{ background: color + "20", color, border: `1px solid ${color}40`, padding: "1px 6px", fontSize: 12, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
      {score}/9
    </span>
  );
}
function RegimeBadge({ fit }: { fit: string }) {
  const map: Record<string, { label: string; color: string }> = {
    growth:   { label: "성장", color: INFO },
    dividend: { label: "배당", color: GOOD },
    neutral:  { label: "중립", color: TEXT_SECONDARY },
  };
  const { label, color } = map[fit] ?? map.neutral;
  return (
    <span style={{ background: color + "20", color, border: `1px solid ${color}40`, padding: "1px 6px", fontSize: 11 }}>
      {label}
    </span>
  );
}

// 밸류 등급은 "싼 편"만 GOOD으로 칠하고 "비싼 편"은 CAUTION까지만 쓴다 - 비싼 게
// 재무 문제는 아니라서, F-Score 탈락과 같은 BAD(빨강)로 보이면 안 된다.
const TIER_COLOR: Record<string, string> = {
  "싼 편": GOOD,
  "중간": WARN,
  "비싼 편": CAUTION,
};
function ValuationBadge({ tier }: { tier?: string | null }) {
  if (!tier) return <span style={{ color: TEXT_FAINT }}>-</span>;
  const color = TIER_COLOR[tier] ?? TEXT_SECONDARY;
  return (
    <span style={{ background: color + "20", color, border: `1px solid ${color}40`, padding: "1px 6px", fontSize: 11, whiteSpace: "nowrap" }}>
      {tier}
    </span>
  );
}

// PSR·PER을 한 칸에 같이 둔다 - 배지(등급)가 먼저 눈에 들어오고, 근거 숫자는 그
// 옆에서 확인하는 순서라 칸을 따로 벌릴 만큼 각각 독립적으로 보지 않는다.
// 자릿수는 상세 카드와 맞춘다 - 같은 값이 표에서 "2.5", 상세에서 "2.46"으로 보이면
// 다른 숫자처럼 읽힌다. PSR은 1 미만이 흔해 두 자리, PER은 한 자리면 충분하다.
const fmtPsr = (v?: number | null) => (v == null ? "-" : v >= 100 ? v.toFixed(0) : v.toFixed(2));
const fmtPer = (v?: number | null) => (v == null ? "-" : v >= 100 ? v.toFixed(0) : v.toFixed(1));

// ── 같은 업종 후보 중앙값 (2026-10-19) ───────────────────────────────────────
// 밸류 등급은 같은 시장 후보 전체 안의 위치라서, 은행처럼 업종 자체가 싼 곳은 늘 "싼 편"이 된다.
// 같은 시장·같은 업종 후보의 중앙값을 옆에 두어 그걸 가려 보게 한다. 순위·판정은 만들지 않는다
// (원칙 1) - 숫자만 나란히. 값이 있는 후보가 PEER_MIN곳 미만이면 중앙값을 내지 않는다.
const PEER_MIN = 5;
type PeerStats = {
  sector: string;
  psr: number | null; nPsr: number;
  per: number | null; nPer: number;
  fcf: number | null; nFcf: number;
};
function median(xs: number[]): number | null {
  if (xs.length === 0) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
const peerKey = (c: { market: string; sector: string | null }) => `${c.market}|${c.sector ?? ""}`;
function buildPeerStats(cands: Candidate[]): Record<string, PeerStats> {
  const groups: Record<string, Candidate[]> = {};
  for (const c of cands) {
    if (!c.sector || c.sector === "Unknown") continue;   // 업종을 모르면 비교하지 않는다
    (groups[peerKey(c)] ??= []).push(c);
  }
  const out: Record<string, PeerStats> = {};
  for (const [key, list] of Object.entries(groups)) {
    const psr = list.map((c) => c.psr).filter((v): v is number => v != null);
    const per = list.map((c) => c.per).filter((v): v is number => v != null);   // 적자 기업은 PER이 없다
    const fcf = list.map((c) => c.fcf_yield_3y).filter((v): v is number => v != null);
    out[key] = {
      sector: list[0].sector as string,
      psr: psr.length >= PEER_MIN ? median(psr) : null, nPsr: psr.length,
      per: per.length >= PEER_MIN ? median(per) : null, nPer: per.length,
      fcf: fcf.length >= PEER_MIN ? median(fcf) : null, nFcf: fcf.length,
    };
  }
  return out;
}

function ValuationNumbers({ psr, per }: { psr?: number | null; per?: number | null }) {
  return (
    <span style={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
      <span style={{ color: psr == null ? TEXT_FAINT : NUM }}>{fmtPsr(psr)}</span>
      <span style={{ color: TEXT_FAINT }}> / </span>
      <span style={{ color: per == null ? TEXT_FAINT : NUM }}>{fmtPer(per)}</span>
    </span>
  );
}

// 성장 등급은 밸류와 달리 절대 기준(0%, 10%)이다 - "역성장"을 BAD(빨강)로 칠하지
// 않는다. 빨강은 F-Score 탈락 같은 재무 부실에 쓰는 색이고, 역성장은 재무 부실이
// 아니다(밸류의 "비싼 편"에 CAUTION까지만 쓴 것과 같은 규칙).
const GROWTH_TIER_COLOR: Record<string, string> = {
  "성장": GOOD,
  "정체": WARN,
  "역성장": CAUTION,
};
// prefix: "3년"(연간 3년 CAGR 판정) / "분기"(최근 분기 매출 전년동기 판정) - 기준이 다른 두 판정을 나란히 둘 때 구분용.
function GrowthBadge({ tier, prefix, title }: { tier?: string | null; prefix?: string; title?: string }) {
  if (!tier) return prefix ? null : <span style={{ color: TEXT_FAINT }}>-</span>;
  const color = GROWTH_TIER_COLOR[tier] ?? TEXT_SECONDARY;
  return (
    <span title={title} style={{ background: color + "20", color, border: `1px solid ${color}40`, padding: "1px 6px", fontSize: 11, whiteSpace: "nowrap" }}>
      {prefix && <span style={{ opacity: 0.75 }}>{prefix} </span>}{tier}
    </span>
  );
}

const quarterLabel = (q?: string | null) => (q ? `${q.slice(2, 4)}년 ${q.slice(-1)}분기` : "최근 분기");

// 성장률은 음수도 흔해 부호를 항상 보여준다(밸류처럼 항상 양수인 배수와 다르다).
const fmtGrowthPct = (v?: number | null) =>
  v == null ? "-" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;

function GrowthNumbers({ cagr3y, yoy }: { cagr3y?: number | null; yoy?: number | null }) {
  return (
    <span style={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
      <span style={{ color: cagr3y == null ? TEXT_FAINT : cagr3y >= 0 ? NUM : CAUTION }}>{fmtGrowthPct(cagr3y)}</span>
      <span style={{ color: TEXT_FAINT }}> / </span>
      <span style={{ color: yoy == null ? TEXT_FAINT : yoy >= 0 ? NUM : CAUTION }}>{fmtGrowthPct(yoy)}</span>
    </span>
  );
}

// ── 지표 설명 팝업 ────────────────────────────────────────────────────────────
function InfoModal({ info, onClose }: { info: typeof INDICATOR_INFO[keyof typeof INDICATOR_INFO]; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.7)" }} onClick={onClose}>
      <div className="p-5 max-w-sm w-full space-y-3" style={{ background: PANEL_BG, border: `1px solid ${BORDER}` }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="text-[14px] font-bold" style={{ color: TEXT_PRIMARY }}>{info.title}</h3>
          <button onClick={onClose} style={{ color: TEXT_MUTED }}><X size={15} /></button>
        </div>
        <p className="text-[12px] leading-relaxed" style={{ color: TEXT_SECONDARY }}>{info.desc}</p>
        <div className="space-y-1.5">
          {info.levels.map((l) => (
            <div key={l.range} className="flex items-center gap-2">
              <span className="text-[11px] font-bold w-16 shrink-0" style={{ color: l.color }}>{l.range}</span>
              <span className="text-[11px]" style={{ color: TEXT_MUTED }}>{l.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── 네러티브 브리프 (Perplexity 실시간 검색) ─────────────────────────────────
const SENTIMENT_STYLE: Record<string, { label: string; color: string; emoji: string }> = {
  HOT:  { label: "시장 관심 높음", color: BAD, emoji: "🔥" },
  WARM: { label: "꾸준한 관심",    color: WARN, emoji: "🌤" },
  COLD: { label: "시장 관심 밖",   color: INFO, emoji: "❄️" },
};

function NarrativeSection({ c }: { c: Candidate }) {
  const [brief, setBrief]     = useState<NarrativeBrief | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      setPending(false);
      try {
        const params = new URLSearchParams({ market: c.market, symbol: c.symbol });
        const res = await fetch(`/api/watchlist/narrative?${params}`);
        const data = await res.json();
        if (cancelled) return;
        if (res.status === 404 && data.pending) { setPending(true); return; }
        if (!res.ok) throw new Error(data.error ?? "요청 실패");
        setBrief(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "네러티브를 불러오지 못했어요");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [c.market, c.symbol]);

  const sent = brief ? (SENTIMENT_STYLE[brief.sentiment] ?? SENTIMENT_STYLE.WARM) : null;

  return (
    <div>
      <div className="p-3 space-y-2.5" style={{ background: INSET_BG, border: `1px solid ${BORDER}` }}>
        <p className="text-[12px] font-semibold" style={{ color: TEXT_SECONDARY }}>네러티브 브리프 — 투자 논리</p>

        {loading && (
          <p className="text-[12px] animate-pulse" style={{ color: TEXT_SECONDARY }}>불러오는 중...</p>
        )}
        {pending && !loading && (
          <p className="text-[12px]" style={{ color: TEXT_SECONDARY }}>
            아직 네러티브가 생성되지 않았어요. 다음 주간 워치리스트 스크리닝(주 1회 자동 실행) 후 표시돼요.
          </p>
        )}
        {error && !loading && (
          <p className="text-[12px]" style={{ color: BAD }}>{error}</p>
        )}

        {brief && !loading && (
          <>
            {sent && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[12px] font-bold px-2 py-0.5" style={{ background: sent.color + "20", color: sent.color, border: `1px solid ${sent.color}40` }}>
                  {sent.emoji} {sent.label}
                </span>
                {brief.trend === "up" && brief.prev_sentiment && (
                  <span className="text-[12px] font-bold px-2 py-0.5" style={{ background: BAD + "20", color: BAD, border: `1px solid ${BAD}40` }}>
                    ▲ 관심도 상승 ({brief.prev_sentiment}→{brief.sentiment})
                  </span>
                )}
                {brief.trend === "down" && brief.prev_sentiment && (
                  <span className="text-[12px] font-bold px-2 py-0.5" style={{ background: INFO + "20", color: INFO, border: `1px solid ${INFO}40` }}>
                    ▼ 관심도 하락 ({brief.prev_sentiment}→{brief.sentiment})
                  </span>
                )}
                {brief.sentiment_reason && (
                  <span className="text-[12px]" style={{ color: TEXT_SECONDARY }}>{brief.sentiment_reason}</span>
                )}
              </div>
            )}

            <p className="text-[12px] leading-relaxed" style={{ color: TEXT_BODY }}>{brief.story}</p>

            {brief.catalysts.length > 0 && (
              <div>
                <p className="text-[12px] font-bold mb-1" style={{ color: GOOD }}>▲ 다가오는 촉매</p>
                {brief.catalysts.map((t, i) => (
                  <p key={i} className="text-[12px] leading-relaxed pl-2" style={{ color: TEXT_SECONDARY }}>· {t}</p>
                ))}
              </div>
            )}
            {brief.risks.length > 0 && (
              <div>
                <p className="text-[12px] font-bold mb-1" style={{ color: BAD }}>▼ 스토리가 깨지는 경우</p>
                {brief.risks.map((t, i) => (
                  <p key={i} className="text-[12px] leading-relaxed pl-2" style={{ color: TEXT_SECONDARY }}>· {t}</p>
                ))}
              </div>
            )}

            <div className="flex items-center justify-between pt-1" style={{ borderTop: `1px solid ${BORDER}` }}>
              <span className="text-[12px]" style={{ color: TEXT_MUTED }}>
                최근 1주 뉴스 기반 GPT 분석 · 참고용 · {brief.cached_at.slice(0, 10)} 갱신
              </span>
              {brief.sources.length > 0 && (
                <span className="flex gap-1.5">
                  {brief.sources.slice(0, 3).map((url, i) => (
                    <a key={i} href={url} target="_blank" rel="noopener noreferrer" className="text-[12px] underline" style={{ color: TEXT_MUTED }}>
                      출처{i + 1}
                    </a>
                  ))}
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── 종목 정성 체크리스트 (종목별 독립 저장) ──────────────────────────────────
interface ChecklistItem { id: string; text: string; checked: boolean }

// 내부자 장내 매수(2026-10-21) - 최근 180일 공시. 없으면 칸을 숨긴다. 금액은 공시 단가 × 주식 수.
interface InsiderTrade { filing_id: string; filed_on: string; trade_date: string | null; owner: string; role: string | null;
  shares: number | null; price: number | null; value: number | null; plan: number | boolean | null }
function InsiderSection({ c }: { c: Candidate }) {
  const [trades, setTrades] = useState<InsiderTrade[]>([]);
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/watchlist/insider?market=${c.market}&symbol=${encodeURIComponent(c.symbol)}`)
      .then((r) => r.json())
      .then((d) => { if (!cancelled) setTrades(d.trades ?? []); })
      .catch(() => { if (!cancelled) setTrades([]); });
    return () => { cancelled = true; };
  }, [c.market, c.symbol]);
  if (trades.length === 0) return null;
  const kr = c.market === "KR";
  const money = (v: number | null) => v == null ? "-" : kr
    ? (v >= 1e8 ? `${(v / 1e8).toFixed(1)}억원` : `${Math.round(v / 1e4).toLocaleString()}만원`)
    : (v >= 1e6 ? `$${(v / 1e6).toFixed(2)}M` : `$${Math.round(v / 1e3).toLocaleString()}K`);
  const buyers = new Set(trades.map((t) => t.owner)).size;
  return (
    <div className="p-3" style={{ background: INSET_BG, border: `1px solid ${BORDER}` }}>
      <p className="text-[12px] font-semibold mb-1.5" style={{ color: TEXT_SECONDARY }}>
        내부자 장내 매수 — 최근 6개월 {buyers}명 · {trades.length}건
      </p>
      <div className="space-y-0.5">
        {trades.map((t, i) => (
          <p key={`${t.filing_id}-${i}`} className="text-[12px] flex flex-wrap gap-x-2" style={{ fontVariantNumeric: "tabular-nums" }}>
            <span style={{ color: TEXT_SECONDARY }}>{(t.trade_date ?? t.filed_on).slice(2)}</span>
            <span className="text-white">{t.owner}</span>
            {t.role && t.role !== "-" && <span style={{ color: TEXT_SECONDARY }}>{t.role}</span>}
            <span>{t.shares != null ? `${Math.round(t.shares).toLocaleString()}주` : "-"}
              {t.price != null && <span style={{ color: TEXT_SECONDARY }}> @{kr ? Math.round(t.price).toLocaleString() : t.price.toFixed(2)}</span>}
            </span>
            <span style={{ color: GOOD }}>{money(t.value)}</span>
            {Boolean(t.plan) && <span style={{ color: TEXT_SECONDARY }} title="10b5-1: 미리 정해 둔 계획 매수">계획 매수</span>}
          </p>
        ))}
      </div>
      <p className="text-[11px] mt-1.5" style={{ color: TEXT_SECONDARY }}>
        {kr ? "DART 임원ㆍ주요주주 소유보고" : "SEC Form 4"} · 장내에서 직접 산 것만(스톡옵션·증여·장외 제외)
      </p>
    </div>
  );
}

// 미국 8-K 주요 공시(2026-10-21) - 최근 180일. 종류는 항목 번호, 아래 줄은 원문 첫머리(번역·요약 없음). 없으면 칸을 숨긴다.
interface Us8kFiling { accession: string; filed_on: string; url: string | null; warn: boolean;
  items: { item: string; label: string; warn: boolean; excerpt?: string | null }[] }
function Us8kSection({ c }: { c: Candidate }) {
  const [filings, setFilings] = useState<Us8kFiling[]>([]);
  useEffect(() => {
    if (c.market !== "US") { setFilings([]); return; }
    let cancelled = false;
    fetch(`/api/watchlist/us8k?symbol=${encodeURIComponent(c.symbol)}`)
      .then((r) => r.json())
      .then((d) => { if (!cancelled) setFilings(d.filings ?? []); })
      .catch(() => { if (!cancelled) setFilings([]); });
    return () => { cancelled = true; };
  }, [c.market, c.symbol]);
  if (filings.length === 0) return null;
  return (
    <div className="p-3" style={{ background: INSET_BG, border: `1px solid ${BORDER}` }}>
      <p className="text-[12px] font-semibold mb-1.5" style={{ color: TEXT_SECONDARY }}>주요 공시 8-K — 최근 6개월 {filings.length}건</p>
      <div className="space-y-1.5">
        {filings.map((f) => (
          <div key={f.accession} className="text-[12px]">
            <p className="flex flex-wrap gap-x-2">
              <span style={{ color: TEXT_SECONDARY, fontVariantNumeric: "tabular-nums" }}>{f.filed_on.slice(2)}</span>
              {f.items.map((i) => <span key={i.item} style={{ color: i.warn ? BAD : "#fff" }}>{i.label}</span>)}
              {f.url && <a href={f.url} target="_blank" rel="noreferrer" className="hover:underline" style={{ color: TEXT_SECONDARY }}>원문↗</a>}
            </p>
            {f.items.filter((i) => i.excerpt).slice(0, 1).map((i) => (
              <p key={i.item} className="text-[11px] line-clamp-2" style={{ color: TEXT_SECONDARY }} title={i.excerpt ?? ""}>{i.excerpt}</p>
            ))}
          </div>
        ))}
      </div>
      <p className="text-[11px] mt-1.5" style={{ color: TEXT_SECONDARY }}>
        SEC 8-K · 실적 발표만 있는 것은 뺌 · 임원 변동의 사임/선임은 원문 낱말로 나눈 것
      </p>
    </div>
  );
}

// 후보가 아닌 종목으로 들어왔을 때(브리핑 "관심 밖 내부자 매수" 등, 2026-10-21) - 트랩 필터 판정과 사유, 내부자 장내 매수·8-K.
// 탈락이어도 왜 떨어졌는지가 정보다. 판정이 없으면 "미확인"(원칙 4).
function MissDetail({ market, symbol }: { market: string; symbol: string }) {
  const [sc, setSc] = useState<{ status: string; piotroski: number | null; reasons: string[]; screened_at: string } | null | undefined>(undefined);
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/watchlist/screening?market=${market}&symbol=${encodeURIComponent(symbol)}`)
      .then((r) => r.json())
      .then((d) => { if (!cancelled) setSc(d.screening ?? null); })
      .catch(() => { if (!cancelled) setSc(null); });
    return () => { cancelled = true; };
  }, [market, symbol]);
  const c = { market, symbol } as Candidate;
  const label = sc === undefined ? "확인 중..." : !sc ? "트랩 필터 판정 없음(미확인 - 스크리닝 대상 밖이거나 아직 안 돌았음)"
    : sc.status === "pass" ? `트랩 필터 통과${sc.piotroski != null ? ` (F-Score ${sc.piotroski})` : ""}`
    : sc.status === "fail" ? "트랩 필터 탈락" : "트랩 필터 데이터부족(계산 못 한 항목이 있음 - 탈락 아님)";
  return (
    <div style={{ flexBasis: "100%" }} className="space-y-2">
      <p style={{ color: sc?.status === "fail" ? BAD : sc?.status === "pass" ? GOOD : TEXT_SECONDARY, fontSize: 12 }}>
        {label}
        {sc?.status === "fail" && sc.reasons.length > 0 && <span style={{ color: TEXT_SECONDARY }}> — {sc.reasons.slice(0, 4).join(" · ")}</span>}
        {sc?.screened_at && <span style={{ color: TEXT_SECONDARY }}> · {String(sc.screened_at).slice(0, 10)} 기준</span>}
      </p>
      <Us8kSection c={c} />
      <InsiderSection c={c} />
    </div>
  );
}

function ChecklistSection({ c }: { c: Candidate }) {
  const [items, setItems] = useState<ChecklistItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/watchlist/checklist?market=${c.market}&symbol=${c.symbol}`)
      .then((r) => r.json())
      .then((d) => { if (!cancelled) setItems(d.items ?? []); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [c.market, c.symbol]);

  const toggle = (id: string) => {
    const next = items.map((it) => (it.id === id ? { ...it, checked: !it.checked } : it));
    setItems(next);
    fetch("/api/watchlist/checklist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ market: c.market, symbol: c.symbol, items: next }),
    }).catch(() => {});
  };

  if (loading) return <div className="h-20 animate-pulse" style={{ background: INSET_BG }} />;

  const checkedCount = items.filter((it) => it.checked).length;

  return (
    <div className="p-3 space-y-1.5" style={{ background: INSET_BG, border: `1px solid ${BORDER}` }}>
      <div className="flex items-center justify-between mb-0.5">
        <p className="text-[12px] font-semibold" style={{ color: TEXT_SECONDARY }}>정성 체크</p>
        <span className="text-[12px]" style={{ color: checkedCount === items.length && items.length > 0 ? GOOD : TEXT_MUTED }}>
          {checkedCount}/{items.length}
        </span>
      </div>
      {items.map((it) => (
        <button
          key={it.id}
          onClick={() => toggle(it.id)}
          className="w-full flex items-start gap-2 text-left py-1"
          style={{ background: "transparent", border: "none", cursor: "pointer" }}
        >
          <span
            className="mt-0.5 shrink-0 w-3.5 h-3.5 flex items-center justify-center"
            style={{
              background: it.checked ? GOOD + "33" : PANEL_BG,
              border: `1.5px solid ${it.checked ? GOOD : BORDER_CTRL}`,
            }}
          >
            {it.checked && <span style={{ color: GOOD, fontSize: 9, fontWeight: 900 }}>✓</span>}
          </span>
          <span className="text-[12px] leading-snug" style={{ color: it.checked ? TEXT_MUTED : TEXT_BODY }}>
            {it.text}
          </span>
        </button>
      ))}
    </div>
  );
}

// ── 종목 상세 팝업 ────────────────────────────────────────────────────────────
function DetailModal({ c, peer, inList, note, onAdd, onSaveNote, onClose }: {
  c: Candidate; peer?: PeerStats; inList: boolean; note: string | null;
  onAdd: () => void; onSaveNote: (note: string) => void; onClose: () => void;
}) {
  const [editingNote, setEditingNote] = useState(false);
  const [noteDraft, setNoteDraft] = useState(note ?? "");
  const [observing, setObserving] = useState(false);
  const [observed, setObserved] = useState(false);
  const [relatedThemes, setRelatedThemes] = useState<{ theme_id: string; label: string | null; linkage?: string }[]>([]);

  // 이 종목이 어느 테마 레이더 테마에 속하는지 (Phase B에서 한국도 지원).
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/radar/ticker-themes?symbol=${encodeURIComponent(c.symbol)}&market=${c.market}`)
      .then((r) => r.json())
      .then((d) => { if (!cancelled) setRelatedThemes(d.themes ?? []); })
      .catch(() => { if (!cancelled) setRelatedThemes([]); });
    return () => { cancelled = true; };
  }, [c.market, c.symbol]);

  const coverColor = (v: number | null) => {
    if (!v) return TEXT_MUTED;
    return v >= 5 ? GOOD : v >= 3 ? WARN : v >= 1 ? CAUTION : BAD;
  };
  const debtColor = (v: number | null) => {
    if (!v) return TEXT_MUTED;
    return v <= 100 ? GOOD : v <= 150 ? WARN : v <= 200 ? CAUTION : BAD;
  };

  // 한 줄 결론 — 이미 있는 값(재무 건전성·체제 성격)으로 즉석 요약 (별도 API 없음, 순위 아님)
  const conclParts: string[] = [];
  if (c.piotroski != null) conclParts.push(c.piotroski >= 7 ? "재무 우수" : c.piotroski >= 5 ? "재무 양호" : "재무 보통");
  conclParts.push(c.regime_fit === "growth" ? "성장주 성격" : c.regime_fit === "dividend" ? "배당주 성격" : "중립 성격");
  const conclusion = conclParts.join(" · ");

  // 칸 제목. 예전엔 10px·대문자·넓은 자간이라 한글이 흩어져 보이고 거의 안 보였다(2026-10-04 사용자 지적).
  const eyebrow = "text-[12px] font-semibold";
  const insetCard = { background: INSET_BG, border: `1px solid ${BORDER}` };

  return (
    // 우측 슬라이드오버 — 목록을 뒤에 남기고 상세만 오른쪽에서 밀려나온다
    <div className="fixed inset-0 z-50 flex justify-end" style={{ background: "rgba(0,0,0,0.5)" }} onClick={onClose}>
      <div className="slideover-panel h-full w-full overflow-y-auto"
        style={{ maxWidth: 780, background: PANEL_BG, borderLeft: `1px solid ${BORDER_CTRL}`, boxShadow: "-24px 0 60px rgba(0,0,0,0.5)" }}
        onClick={(e) => e.stopPropagation()}>

        {/* 헤더 — 스크롤해도 상단 고정 */}
        <div className="sticky top-0 z-10 flex items-start justify-between px-5 py-4"
          style={{ background: PANEL_BG, borderBottom: `1px solid ${BORDER}` }}>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[12px] font-bold px-2 py-0.5" style={{ background: c.market === "US" ? INFO + "20" : BAD + "20", color: c.market === "US" ? INFO : BAD }}>{c.market}</span>
              <RegimeBadge fit={c.regime_fit} />
            </div>
            <div className="flex items-baseline gap-2">
              <h2 className="text-2xl font-black" style={{ color: NUM, letterSpacing: "-0.01em" }}>{c.symbol}</h2>
              {c.current_price != null && (
                <span className="text-[13px]" style={{ color: TEXT_SECONDARY, fontVariantNumeric: "tabular-nums" }}>{formatPrice(c.market, c.current_price)} <span style={{ color: TEXT_MUTED }}>(스크리닝 시점가)</span></span>
              )}
            </div>
            {c.name && <p className="text-[13px] mt-0.5" style={{ color: TEXT_SECONDARY }}>{c.name}</p>}
            {c.sector && <p className="text-[12px] mt-0.5" style={{ color: TEXT_SECONDARY }}>{c.sector} · {formatCap(c.market, c.market_cap)}</p>}
          </div>
          <button onClick={onClose} className="p-1" style={{ color: TEXT_SECONDARY }}><X size={18} /></button>
        </div>

        <div className="p-5 space-y-4">
          {/* 한 줄 결론 */}
          <div className="p-3" style={insetCard}>
            <p className={eyebrow + " mb-1"} style={{ color: TEXT_SECONDARY }}>한 줄 결론</p>
            <p className="text-[14px] font-semibold" style={{ color: TEXT_PRIMARY }}>{conclusion}</p>
          </div>

          {/* 소속 테마 — 테마 레이더와의 연결 다리 (미국만) */}
          {relatedThemes.length > 0 && (
            <div className="p-3" style={insetCard}>
              <p className={eyebrow + " mb-1.5"} style={{ color: TEXT_SECONDARY }}>테마 레이더 소속</p>
              <div className="flex flex-wrap gap-1.5">
                {relatedThemes.map((t) => {
                  // 간접·시장 인식은 테마 신호(라벨) 계산에 들어가지 않는다 - 라벨을 붙이면
                  // 그 신호가 이 종목에도 해당하는 것처럼 읽히므로 소속 종류만 적는다.
                  const side = t.linkage === "perceived" ? "시장 인식" : t.linkage === "peripheral" ? "간접" : null;
                  return side ? (
                    <a
                      key={t.theme_id}
                      href="/radar"
                      className="text-[12px] px-2.5 py-1 rounded-full transition-opacity hover:opacity-80"
                      style={{ color: side === "시장 인식" ? PERCEIVED_FG : TEXT_MUTED, border: "1px dashed var(--border)" }}
                    >
                      {themeName(t.theme_id).ko} · {side}
                    </a>
                  ) : (
                    <a
                      key={t.theme_id}
                      href="/radar"
                      className="text-[12px] font-semibold px-2.5 py-1 rounded-full transition-opacity hover:opacity-80"
                      style={{ background: ACCENT + "18", color: ACCENT, border: `1px solid ${ACCENT}33` }}
                    >
                      {themeName(t.theme_id).ko}{t.label ? ` · ${labelWithKo(t.label)}` : ""}
                    </a>
                  );
                })}
              </div>
              {relatedThemes.some((t) => t.linkage === "perceived" || t.linkage === "peripheral") && (
                <p className="mt-1.5 text-[11px]" style={{ color: TEXT_MUTED }}>
                  점선 표시는 사업 소속이 아닙니다. 시장 인식은 테마 ETF 편입, 간접은 사업 비중이 작은 경우이며,
                  둘 다 테마 신호 계산에는 들어가지 않습니다.
                </p>
              )}
            </div>
          )}

          {/* 2단: 투자 논리(네러티브) | 기술적 타이밍(차트) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
            <NarrativeSection c={c} />
            <div>
              <p className={eyebrow + " mb-1.5"} style={{ color: TEXT_SECONDARY }}>기술적 타이밍</p>
              <StockTechPanel market={c.market} symbol={c.symbol} />
            </div>
          </div>

          {/* 핵심 재무·체제 지표 — 이 종목이 왜 후보인지에 대한 근거 (순위 아님) */}
          <div>
            <p className={eyebrow + " mb-1.5"} style={{ color: TEXT_SECONDARY }}>핵심 재무 · 체제 지표</p>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {/* F-Score */}
              <div className="p-3" style={insetCard}>
                <p className={eyebrow + " mb-1"} style={{ color: TEXT_SECONDARY }}>Piotroski F-Score</p>
                <p className="text-2xl font-black" style={{ color: c.piotroski != null ? (c.piotroski >= 7 ? GOOD : c.piotroski >= 5 ? WARN : BAD) : TEXT_MUTED, fontVariantNumeric: "tabular-nums" }}>
                  {c.piotroski ?? "-"}<span className="text-sm font-normal" style={{ color: TEXT_MUTED }}>/9</span>
                </p>
                <p className="text-[12px] mt-1" style={{ color: TEXT_SECONDARY }}>
                  {c.piotroski != null ? (c.piotroski >= 7 ? "재무 우수" : c.piotroski >= 5 ? "보통 수준" : "취약") : "데이터 없음"}
                </p>
              </div>

              {/* 부채비율 */}
              <div className="p-3" style={insetCard}>
                <p className={eyebrow + " mb-1"} style={{ color: TEXT_SECONDARY }}>부채비율</p>
                {c.debt_ratio != null ? (
                  <p className="text-2xl font-black" style={{ color: debtColor(c.debt_ratio), fontVariantNumeric: "tabular-nums" }}>{c.debt_ratio}%</p>
                ) : (
                  <p className="text-[15px] font-black leading-7" style={{ color: NOTE_COLOR[c.data_notes?.debt ?? ""] ?? TEXT_MUTED }}>
                    {c.data_notes?.debt ?? "-"}
                  </p>
                )}
                <p className="text-[12px] mt-1" style={{ color: TEXT_SECONDARY }}>
                  {c.data_notes?.debt === "자본잠식(음수 자본)" ? "자기자본 음수 — 원인 확인 필요" : "총부채 / 자기자본"}
                </p>
              </div>

              {/* 이자보상배율 */}
              <div className="p-3" style={insetCard}>
                <p className={eyebrow + " mb-1"} style={{ color: TEXT_SECONDARY }}>이자보상배율</p>
                {c.interest_coverage != null ? (
                  <p className="text-2xl font-black" style={{ color: coverColor(c.interest_coverage), fontVariantNumeric: "tabular-nums" }}>{c.interest_coverage.toFixed(1)}x</p>
                ) : (
                  <p className="text-[15px] font-black leading-7" style={{ color: NOTE_COLOR[c.data_notes?.interest ?? ""] ?? TEXT_MUTED }}>
                    {c.data_notes?.interest ?? "-"}
                  </p>
                )}
                <p className="text-[12px] mt-1" style={{ color: TEXT_SECONDARY }}>
                  {c.data_notes?.interest === "무차입" ? "이자비용 없음 — 무차입" : "영업이익 / 이자비용"}
                </p>
              </div>

              {/* 영업현금흐름 */}
              <div className="p-3" style={insetCard}>
                <p className={eyebrow + " mb-1"} style={{ color: TEXT_SECONDARY }}>영업현금흐름</p>
                <p className="text-2xl font-black" style={{ color: c.cfo_positive_count >= 2 ? GOOD : c.cfo_positive_count === 1 ? WARN : BAD, fontVariantNumeric: "tabular-nums" }}>
                  {c.cfo_positive_count}/2
                </p>
                <p className="text-[12px] mt-1" style={{ color: TEXT_SECONDARY }}>최근 2년 중 플러스 연도</p>
              </div>
            </div>

            {/* 밸류 위치 — 위 4칸이 전부 "튼튼한가"라서, "싼가"는 따로 한 줄로 둔다.
                단독 카드로 두는 이유: 위 격자에 끼워 넣으면 재무 건전성 지표처럼
                읽히는데 이건 판단 기준이 다르다(같은 시장 후보와의 상대 위치). */}
            <div className="p-3 mt-3" style={insetCard}>
              <p className={eyebrow + " mb-1"} style={{ color: TEXT_SECONDARY }}>밸류 위치 (같은 시장 후보 중)</p>
              <div className="flex items-center gap-2 flex-wrap">
                <ValuationBadge tier={c.valuation_tier} />
                <span className="text-[12px]" style={{ color: TEXT_SECONDARY, fontVariantNumeric: "tabular-nums" }}>
                  PSR {fmtPsr(c.psr)}
                  <span style={{ color: TEXT_MUTED }}> · </span>
                  PER {fmtPer(c.per)}
                </span>
              </div>
              <p className="text-[12px] mt-1" style={{ color: TEXT_SECONDARY }}>
                {c.valuation_tier
                  ? "최근 4분기 매출·순이익 합 기준. 절대적으로 싸다는 뜻이 아니라 후보들 중 위치입니다."
                  : c.psr != null
                    ? "후보 중 PSR을 구한 곳이 3곳 미만이라 등급을 나누지 않습니다."
                    : "최근 4분기 재무나 시가총액이 없어 계산할 수 없습니다."}
                {c.psr != null && c.per == null && " 순이익 합이 0 이하여서 PER은 표시하지 않습니다."}
              </p>
              {peer && (
                <p className="text-[12px] mt-1" style={{ color: TEXT_SECONDARY, fontVariantNumeric: "tabular-nums" }}>
                  {peer.psr != null || peer.per != null ? (
                    <>
                      같은 업종({peer.sector}) 후보 중앙값: PSR {fmtPsr(peer.psr)}
                      <span style={{ color: TEXT_MUTED }}> ({peer.nPsr}곳)</span>
                      <span style={{ color: TEXT_MUTED }}> · </span>
                      PER {fmtPer(peer.per)}
                      <span style={{ color: TEXT_MUTED }}> ({peer.nPer}곳)</span>
                      <span style={{ color: TEXT_MUTED }}> - 업종 전체가 아니라 필터 통과 후보 중</span>
                    </>
                  ) : (
                    <span style={{ color: TEXT_MUTED }}>같은 업종({peer.sector}) 후보가 {PEER_MIN}곳 미만이라 업종 비교를 하지 않습니다.</span>
                  )}
                </p>
              )}
            </div>

            {/* 현금 창출 — FCF 수익률. 등급·색 판정을 하지 않는다(업종마다 정상 범위가 너무 달라
                하나의 기준선이 거짓 라벨을 만든다 - src/analyzers/company_cashflow.py). 음수만 주의 색. */}
            <div className="p-3 mt-3" style={insetCard}>
              <p className={eyebrow + " mb-1"} style={{ color: TEXT_SECONDARY }}>현금 창출 (FCF 수익률)</p>
              {c.fcf_yield_3y != null || c.fcf_yield_latest != null ? (
                <p className="text-[13px]" style={{ color: TEXT_SECONDARY, fontVariantNumeric: "tabular-nums" }}>
                  3년 평균{" "}
                  <span className="font-bold" style={{ color: c.fcf_yield_3y == null ? TEXT_MUTED : c.fcf_yield_3y < 0 ? CAUTION : NUM }}>
                    {c.fcf_yield_3y == null ? "-" : `${(c.fcf_yield_3y * 100).toFixed(1)}%`}
                  </span>
                  <span style={{ color: TEXT_MUTED }}> · </span>
                  {c.fcf_latest_year ?? "최근"}년{" "}
                  <span style={{ color: c.fcf_yield_latest == null ? TEXT_MUTED : c.fcf_yield_latest < 0 ? CAUTION : NUM }}>
                    {c.fcf_yield_latest == null ? "-" : `${(c.fcf_yield_latest * 100).toFixed(1)}%`}
                  </span>
                  {c.fcf_negative_years != null && c.fcf_negative_years > 0 && (
                    <span style={{ color: CAUTION }}> · 3년 중 {c.fcf_negative_years}년 마이너스</span>
                  )}
                  {peer?.fcf != null && (
                    <span style={{ color: TEXT_MUTED }}> · 같은 업종 후보 중앙값 {(peer.fcf * 100).toFixed(1)}% ({peer.nFcf}곳)</span>
                  )}
                </p>
              ) : (
                <p className="text-[13px]" style={{ color: TEXT_MUTED }}>{isFinancialSector(c.sector) ? "해당 없음 (금융업)" : "데이터 부족"}</p>
              )}
              <p className="text-[12px] mt-1" style={{ color: TEXT_SECONDARY }}>
                {isFinancialSector(c.sector) && c.fcf_yield_3y == null && c.fcf_yield_latest == null
                  ? "은행·보험사는 예금·보험료 흐름이 영업현금흐름에 섞여 FCF가 사업의 현금 창출을 뜻하지 않아 계산하지 않습니다."
                  : c.fcf_yield_3y != null
                  ? "잉여현금흐름(영업현금흐름 - 설비투자)을 지금 시가총액으로 나눈 값. 설비투자로 해마다 출렁여서 최근 3개 회계연도 평균을 함께 봅니다. 업종마다 정상 범위가 달라 등급은 매기지 않습니다."
                  : c.fcf_yield_latest != null
                    ? "연속 3개 회계연도 현금흐름이 없어 3년 평균은 계산하지 않았습니다."
                    : "연차 현금흐름표나 시가총액이 없어 계산할 수 없습니다."}
              </p>
            </div>

            {/* 성장 위치 — 밸류와 나란히 두되 기준이 다르다는 걸 문구로 밝힌다.
                밸류는 후보들 중 상대 순위, 성장은 절대 기준(0%/10%) -
                무차입 흑자인데 매출이 줄어드는 가치 함정을 밸류만으로는 못 본다. */}
            <div className="p-3 mt-3" style={insetCard}>
              <p className={eyebrow + " mb-1"} style={{ color: TEXT_SECONDARY }}>성장 위치 (매출 3년 CAGR · 최근 분기, 절대 기준)</p>
              <div className="flex items-center gap-2 flex-wrap">
                <GrowthBadge tier={c.growth_tier} prefix={c.rev_q_tier || c.rev_ttm_tier ? "3년" : undefined} />
                <GrowthBadge tier={c.rev_ttm_tier} prefix="1년" />
                <GrowthBadge tier={c.rev_q_tier} prefix="분기" />
                <span className="text-[12px]" style={{ color: TEXT_SECONDARY, fontVariantNumeric: "tabular-nums" }}>
                  3년 {fmtGrowthPct(c.revenue_cagr_3y)}
                  <span style={{ color: TEXT_MUTED }}> · </span>
                  직전 회계연도 {fmtGrowthPct(c.revenue_yoy)}
                </span>
                {c.op_margin_direction && (
                  <span className="text-[12px]" style={{ color: c.op_margin_direction === "개선" ? GOOD : CAUTION }}>
                    영업이익률 3년 {c.op_margin_direction}
                  </span>
                )}
              </div>
              {c.facts && (c.facts.from_high != null || c.facts.analysts != null) && (
                <p className="text-[12px] mt-1" style={{ color: TEXT_SECONDARY, fontVariantNumeric: "tabular-nums" }}>
                  {c.facts.from_high != null && <>52주 고점 대비 {(c.facts.from_high * 100).toFixed(1)}%</>}
                  {c.facts.from_low != null && <> · 저점 대비 +{(c.facts.from_low * 100).toFixed(1)}%</>}
                  {c.facts.analysts != null && <> · 애널리스트 {c.facts.analysts}명</>}
                  {c.facts.as_of && <span style={{ color: TEXT_MUTED }}> ({Number(c.facts.as_of.slice(5, 7))}/{Number(c.facts.as_of.slice(8, 10))} 기준)</span>}
                </p>
              )}
              {c.surprise && (
                <p className="text-[12px] mt-1" style={{ color: TEXT_SECONDARY, fontVariantNumeric: "tabular-nums" }}>
                  최근 실적 발표 {Number(c.surprise.date.slice(5, 7))}/{Number(c.surprise.date.slice(8, 10))}: EPS 추정치 대비{" "}
                  <span style={{ color: c.surprise.pct > 0 ? GOOD : c.surprise.pct < 0 ? CAUTION : TEXT_MUTED }}>
                    {c.surprise.pct > 0 ? "+" : ""}{c.surprise.pct.toFixed(1)}%
                  </span>
                  {c.surprise.estimate != null && c.surprise.reported != null && (
                    <span style={{ color: TEXT_MUTED }}> (추정 {c.surprise.estimate} → 실제 {c.surprise.reported})</span>
                  )}
                </p>
              )}
              {c.rev_ttm_yoy != null && (
                <p className="text-[12px] mt-1" style={{ color: TEXT_SECONDARY, fontVariantNumeric: "tabular-nums" }}>
                  최근 1년({quarterLabel(c.rev_ttm_quarter)}까지 4개 분기) 매출, 그 전 4개 분기 대비{" "}
                  <span style={{ color: c.rev_ttm_yoy >= 0 ? NUM : CAUTION }}>{fmtGrowthPct(c.rev_ttm_yoy)}</span>
                </p>
              )}
              {c.rev_q_yoy != null && (
                <p className="text-[12px] mt-1" style={{ color: TEXT_SECONDARY, fontVariantNumeric: "tabular-nums" }}>
                  {quarterLabel(c.rev_q_quarter)} 매출 1년 전 같은 분기 대비{" "}
                  <span style={{ color: c.rev_q_yoy >= 0 ? NUM : CAUTION }}>{fmtGrowthPct(c.rev_q_yoy)}</span>
                  {(c.rev_ttm_tier ?? c.rev_q_tier) && c.growth_tier && (c.rev_ttm_tier ?? c.rev_q_tier) !== c.growth_tier && (
                    <span style={{ color: TEXT_MUTED }}> - 3년 기준({c.growth_tier})과 다름: 최근 업황 변화가 아직 연간 실적에 반영되기 전일 수 있습니다</span>
                  )}
                </p>
              )}
              {c.op_margin_q_now != null && (
                <p className="text-[12px] mt-1" style={{ color: TEXT_SECONDARY, fontVariantNumeric: "tabular-nums" }}>
                  최근 분기 영업이익률 {(c.op_margin_q_now * 100).toFixed(1)}%
                  {c.op_margin_q_change != null && (
                    <span style={{ color: c.op_margin_q_status === "개선" ? GOOD : c.op_margin_q_status === "악화" ? CAUTION : TEXT_MUTED }}>
                      {" "}(1년 전 같은 분기 대비 {c.op_margin_q_change >= 0 ? "+" : ""}{(c.op_margin_q_change * 100).toFixed(1)}%p · {c.op_margin_q_status})
                    </span>
                  )}
                </p>
              )}
              <p className="text-[12px] mt-1" style={{ color: TEXT_SECONDARY }}>
                {c.growth_tier
                  ? "3년: 연차 재무제표 최근 4개 회계연도(정확히 3년 간격). 1년: 최근 4개 분기 매출 합을 그 전 4개 분기와 비교(연속 8분기가 있을 때만). 분기: 최근 분기 매출을 1년 전 같은 분기와 비교. 모두 0%/10% 절대 기준이고 합치지 않습니다."
                  : "회계기간이 부족하거나 간격이 맞지 않아 계산할 수 없습니다."}
              </p>
            </div>

            {/* 체제 적합도 */}
            <div className="p-3 mt-3" style={insetCard}>
              <p className={eyebrow + " mb-1"} style={{ color: TEXT_SECONDARY }}>시장 체제 적합도</p>
              <div className="flex items-center gap-2">
                <RegimeBadge fit={c.regime_fit} />
                <span className="text-[12px]" style={{ color: TEXT_SECONDARY }}>
                  {c.regime_fit === "growth" ? "매출/EPS 성장률 높음 — 성장장에 유리" :
                   c.regime_fit === "dividend" ? "배당수익률 2% 이상 — 배당장에 유리" :
                   "뚜렷한 성장·배당 특성 없음"}
                </span>
              </div>
              {/* 유니버스 출처 — 종목 선택 기준이 아니라 "이 후보가 어디서 왔나"를
                  밝히는 한 줄. 중형주(S&P 400)는 2026-09-30에 편입했다. */}
              {c.universe_source && (
                <p className="text-[12px] mt-2" style={{ color: TEXT_SECONDARY }}>
                  유니버스: {c.universe_source === "sp400"
                    ? "S&P 400 (중형주) — 2026-09-30 편입"
                    : "S&P 500 (대형주)"}
                </p>
              )}
            </div>
          </div>

          <Us8kSection c={c} />
          <InsiderSection c={c} />

          {/* 정성 체크 (구 투자 워크북) */}
          <ChecklistSection c={c} />

          {/* 매수 이유 메모 — 워치리스트에 추가된 종목만 */}
          {inList && (
            <div className="p-3" style={insetCard}>
              <p className={eyebrow + " mb-1.5"} style={{ color: TEXT_SECONDARY }}>매수 이유 메모</p>
              {editingNote ? (
                <div className="flex gap-1.5">
                  <input
                    value={noteDraft}
                    onChange={(e) => setNoteDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { onSaveNote(noteDraft.trim()); setEditingNote(false); } if (e.key === "Escape") setEditingNote(false); }}
                    placeholder="담은 이유, 지켜볼 포인트…"
                    autoFocus
                    className="flex-1 px-2.5 py-1.5 text-[12px] outline-none"
                    style={{ background: INPUT_BG, color: TEXT_PRIMARY, border: `1px solid ${BORDER_CTRL}` }}
                  />
                  <button onClick={() => { onSaveNote(noteDraft.trim()); setEditingNote(false); }}
                    className="px-3 text-[12px] font-bold" style={{ background: ACCENT + "18", color: ACCENT, border: `1px solid ${ACCENT}33` }}>저장</button>
                </div>
              ) : (
                <button onClick={() => setEditingNote(true)} className="text-[12px] text-left w-full" style={{ color: note ? TEXT_SECONDARY : TEXT_MUTED, background: "transparent", border: "none", cursor: "pointer" }}>
                  {note || "+ 메모 추가 — 왜 담았는지 기록해두세요"}
                </button>
              )}
            </div>
          )}

          {/* 관찰 노트 - 메모(수시로 고침)와 달리 가설을 고정해 두고 4주·12주 뒤 그때와 지금을 대조 */}
          <button onClick={() => setObserving(true)}
            className="w-full py-2 text-[13px]"
            style={{ background: "transparent", color: observed ? GOOD : TEXT_SECONDARY, border: `1px solid ${BORDER_CTRL}` }}>
            {observed ? "관찰을 남겼습니다 - 관찰 노트에서 4주·12주 뒤 회고" : "✎ 관찰 남기기 (4주·12주 뒤 회고)"}
          </button>
          {observing && (
            <ObservationForm kind="stock" market={c.market as "US" | "KR"} ticker={c.symbol}
              title={c.market === "KR" ? `${c.name ?? c.symbol} (${c.symbol})` : `${c.symbol}${c.name ? ` · ${c.name}` : ""}`}
              onClose={() => setObserving(false)} onSaved={() => setObserved(true)} />
          )}

          {/* 버튼 — 워치리스트 추가 (다음 행동 유도) */}
          <button
            onClick={onAdd}
            disabled={inList}
            className="w-full py-2.5 text-[13px] font-bold transition-opacity disabled:opacity-40"
            style={{ background: inList ? PANEL_BG : ACCENT + "18", color: inList ? TEXT_FAINT : ACCENT, border: `1px solid ${inList ? BORDER : ACCENT + "33"}` }}>
            {inList ? "이미 워치리스트에 추가됨" : "+ 내 워치리스트에 추가"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── 컬럼 헤더 (툴팁) ─────────────────────────────────────────────────────────
type SortKey = "market_cap" | "piotroski" | "debt_ratio" | "interest_coverage" | "psr" | "per" | "revenue_cagr_3y" | "revenue_yoy";
type SortState = { key: SortKey; dir: "asc" | "desc" } | null;
const SORT_LABEL: Record<SortKey, string> = {
  market_cap: "시가총액", piotroski: "F-Score", debt_ratio: "부채비율", interest_coverage: "이자보상",
  psr: "PSR", per: "PER", revenue_cagr_3y: "매출 3년 성장", revenue_yoy: "매출 1년 성장",
};
// 처음 누를 때의 방향 - 그 지표에서 "좋은 쪽"이 위로 오게(부채·PSR·PER은 낮을수록, 나머지는 높을수록).
// 순위를 매기는 게 아니라 사용자가 고른 한 지표로 줄 세워 보는 보기 기능이다(기본은 정렬 없음).
const SORT_FIRST_DIR: Record<SortKey, "asc" | "desc"> = {
  market_cap: "desc", piotroski: "desc", debt_ratio: "asc", interest_coverage: "desc",
  psr: "asc", per: "asc", revenue_cagr_3y: "desc", revenue_yoy: "desc",
};

function ColHeader({ label, infoKey, onInfo, sortKey, sort, onSort, className }: {
  label: string;
  className?: string;
  infoKey?: keyof typeof INDICATOR_INFO;
  onInfo?: (key: keyof typeof INDICATOR_INFO) => void;
  sortKey?: SortKey;
  sort?: SortState;
  onSort?: (key: SortKey) => void;
}) {
  const active = sortKey && sort?.key === sortKey;
  return (
    <th className={className} style={{ padding: "8px 8px", textAlign: "left", fontWeight: 500, whiteSpace: "nowrap" }}>
      <span style={{ display: "flex", alignItems: "center", gap: 4, color: active ? ACCENT : TEXT_SECONDARY, fontSize: 12 }}>
        {sortKey && onSort ? (
          <button onClick={() => onSort(sortKey)} title={`${SORT_LABEL[sortKey]}로 정렬`}
            style={{ background: "transparent", border: "none", padding: 0, cursor: "pointer", color: "inherit", fontSize: 12, fontFamily: "inherit" }}>
            {label}{active ? (sort!.dir === "asc" ? " ▲" : " ▼") : " ↕"}
          </button>
        ) : label}
        {infoKey && onInfo && (
          <button onClick={(e) => { e.stopPropagation(); onInfo(infoKey); }} style={{ color: TEXT_FAINT, lineHeight: 0 }}>
            <Info size={11} />
          </button>
        )}
      </span>
    </th>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function WatchlistPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [myList, setMyList]         = useState<WatchItem[]>([]);
  const [screened_at, setScreenedAt] = useState<string | null>(null);
  const [loading, setLoading]       = useState(true);
  const [tab, setTab]               = useState<"candidates" | "my">("candidates");
  const [marketFilter, setMarketFilter] = useState<"ALL" | "US" | "KR">("ALL");
  const [regimeFilter, setRegimeFilter] = useState<"ALL" | "growth" | "dividend" | "neutral">("ALL");
  const [newOnly, setNewOnly] = useState(false);
  const [cheapOnly, setCheapOnly] = useState(false);
  const [growingOnly, setGrowingOnly] = useState(false);
  const [themeOnly, setThemeOnly] = useState(false);
  const [preset, setPreset] = useState<PresetKey | null>(null);
  // 275종목 중 아는 티커/이름을 바로 찾는 용도 - "새 아이디어 탐색"인 다른 필터들과
  // 달리 "이미 아는 종목이 후보에 있는지"를 확인하는 반대 방향 쓰임새다.
  const [searchQuery, setSearchQuery] = useState("");
  // 지표별 숫자 필터. 빈칸이면 꺼짐. 값이 없는 종목은 그 필터가 켜져 있을 때만 빠지고,
  // 몇 개가 "값 없음"으로 빠졌는지 따로 보여준다(계산 불가를 조용히 탈락시키지 않는다 - 원칙 4).
  const [numFilter, setNumFilter] = useState({ minF: "", maxDebt: "", minInterest: "", maxPsr: "", maxPer: "", minCagr: "" });
  const [showNumFilter, setShowNumFilter] = useState(false);
  const [sort, setSort] = useState<SortState>(null);
  const [addedSymbols, setAddedSymbols] = useState<Set<string>>(new Set());
  const [selected, setSelected]     = useState<Candidate | null>(null);
  const [infoKey, setInfoKey]       = useState<keyof typeof INDICATOR_INFO | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cRes, mRes] = await Promise.all([
        fetch("/api/watchlist/candidates"),
        fetch("/api/watchlist/my"),
      ]);
      const cData = await cRes.json();
      // API 오류면 { error } 객체가 와서 .map에서 터졌다 - 배열일 때만 쓴다(2026-10-04).
      const mJson = await mRes.json();
      const mData: WatchItem[] = Array.isArray(mJson) ? mJson : [];
      setCandidates(cData.candidates ?? []);
      setScreenedAt(cData.screened_at ?? null);
      setMyList(mData);
      setAddedSymbols(new Set(mData.map((w) => `${w.market}:${w.symbol}`)));
    } finally {
      setLoading(false);
    }
  }, []);

  // 최근 주간 갱신에서 관심도가 오른(COLD→WARM/HOT 등) 종목 - 목록 배지와 "관심도 오른 종목만" 필터에 쓴다.
  // 관심도는 뉴스량 기준 보조 정보라 맨 위 배너 대신 목록 안에 둔다(2026-10-05).
  const [shifts, setShifts] = useState<{ market: string; symbol: string; name?: string | null; prev_sentiment: string; sentiment: string }[]>([]);
  const heating = new Map(shifts.map((s) => [`${s.market}:${s.symbol}`, `${s.prev_sentiment}→${s.sentiment}`]));
  const [heatingOnly, setHeatingOnly] = useState(false);
  useEffect(() => {
    fetch("/api/watchlist/narrative-shifts")
      .then((r) => r.json())
      .then((d) => setShifts(d.shifts ?? []))
      .catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  // 다른 화면에서 종목 이름을 누르고 들어온 경우(/watchlist?stock=US:MU, 2026-10-20) - 후보면 상세 카드를 바로 열고,
  // 후보가 아니면 위에 안내와 외부 시세 링크를 띄운다. 처음 불러온 뒤 한 번만(메모 저장 뒤 다시 불러올 때는 무시).
  const [linkMiss, setLinkMiss] = useState<{ market: string; symbol: string; name: string | null; mine: boolean } | null>(null);
  const linkHandled = useRef(false);
  useEffect(() => {
    if (loading || linkHandled.current) return;
    linkHandled.current = true;
    const qs = new URLSearchParams(window.location.search);
    // 개요 "이번 주 변화"에서 넘어온 조합 보기(?preset=turnaround) · 신규만(?new=1)
    const presetParam = qs.get("preset");
    if (presetParam && PRESETS.some((p) => p.key === presetParam)) setPreset(presetParam as PresetKey);
    if (qs.get("new") === "1") setNewOnly(true);
    const raw = qs.get("stock");
    if (!raw || !raw.includes(":")) return;
    const [m, ...rest] = raw.split(":");
    const sym = rest.join(":");
    const c = candidates.find((x) => x.market === m && x.symbol === sym);
    if (c) { setSelected(c); return; }
    const mine = myList.find((w) => w.market === m && w.symbol === sym);
    setLinkMiss({ market: m, symbol: sym, name: mine?.name ?? null, mine: !!mine });
    if (mine) setTab("my");
  }, [loading, candidates, myList]);
  const clearStockParam = () => {
    if (window.location.search.includes("stock=")) window.history.replaceState(null, "", window.location.pathname);
  };

  const addToWatchlist = async (c: Candidate) => {
    await fetch("/api/watchlist/my", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ market: c.market, symbol: c.symbol, name: c.name }),
    });
    load();
  };
  const removeFromWatchlist = async (id: number) => {
    await fetch(`/api/watchlist/my/${id}`, { method: "DELETE" });
    load();
  };

  // 메모 인라인 편집 (내 워치리스트 탭 목록용)
  const [editingNote, setEditingNote] = useState<number | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const saveNote = async (item: WatchItem) => {
    await fetch("/api/watchlist/my", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ market: item.market, symbol: item.symbol, name: item.name, note: noteDraft.trim() || null }),
    });
    setEditingNote(null);
    load();
  };

  // 보유 기록(매수일·매수가·깨지는 조건) 편집. 메모와 따로 두는 이유는, 메모는
  // 수시로 고치는 글이고 이건 한 번 적고 분기마다 들여다보는 기록이라서다.
  const [editingHolding, setEditingHolding] = useState<number | null>(null);
  const [holdDraft, setHoldDraft] = useState({ bought_at: "", buy_price: "", thesis_breaks: "" });
  const startEditHolding = (item: WatchItem) => {
    setEditingHolding(item.id);
    setHoldDraft({
      bought_at: item.bought_at ?? "",
      buy_price: item.buy_price != null ? String(item.buy_price) : "",
      thesis_breaks: item.thesis_breaks ?? "",
    });
  };
  const saveHolding = async (item: WatchItem) => {
    const price = holdDraft.buy_price.trim();
    await fetch("/api/watchlist/my", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        market: item.market, symbol: item.symbol, name: item.name,
        bought_at: holdDraft.bought_at.trim() || null,
        // 숫자로 못 읽히면 저장하지 않는다 - 쓰레기 값이 들어가면 나중에 못 믿는다.
        buy_price: price && Number.isFinite(Number(price)) ? Number(price) : null,
        thesis_breaks: holdDraft.thesis_breaks.trim() || null,
      }),
    });
    setEditingHolding(null);
    load();
  };

  // 상세 팝업에서의 메모 저장 (종목 클릭 → 팝업 내 메모)
  const saveNoteFromModal = async (c: Candidate, note: string) => {
    await fetch("/api/watchlist/my", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ market: c.market, symbol: c.symbol, name: c.name, note: note || null }),
    });
    load();
  };

  // 테마 흐름 판정은 현재 시장 범위에서 한다. 기준은 세 단계로 내려간다:
  //   label   - Quiet 라벨 또는 분기 "조용한 변화" 테마 (본래 기준)
  //   interim - 그런 테마가 없으면 "실적 ↑·주가 ↑ 아님" 테마 (라벨 전 대체 기준)
  //   any     - 그것도 없으면 어느 테마에든 사업 소속 (빈 목록을 보여 주지 않는다)
  // 어느 기준인지 버튼 이름과 안내 문구에 그대로 적는다.
  const inMarket = candidates.filter((c) => marketFilter === "ALL" || c.market === marketFilter);
  const themesKnown = candidates.some((c) => Array.isArray(c.themes));
  const countBy = (f: (t: ThemeRef) => boolean) => inMarket.filter((c) => (c.themes ?? []).some(f)).length;
  const flowMode: "label" | "interim" | "any" = countBy(isFlowTheme) > 0 ? "label" : countBy(isInterimFlow) > 0 ? "interim" : "any";
  const flowTest = flowMode === "label" ? isFlowTheme : flowMode === "interim" ? isInterimFlow : null;
  const inTheme = (c: Candidate) => flowTest ? (c.themes ?? []).some(flowTest) : (c.themes ?? []).length > 0;
  const themeCount = inMarket.filter(inTheme).length;
  const heatingCount = inMarket.filter((c) => heating.has(`${c.market}:${c.symbol}`)).length;
  const presetCounts = Object.fromEntries(PRESETS.map((p) => [p.key, inMarket.filter(p.test).length])) as Record<PresetKey, number>;
  const activePreset = PRESETS.find((p) => p.key === preset) ?? null;

  // 업종 중앙값은 필터를 건 목록이 아니라 시장 전체 후보로 낸다 - 필터에 따라 기준이 바뀌면 안 된다.
  const peerStats = useMemo(() => buildPeerStats(candidates), [candidates]);

  const filtered = candidates.filter((c) => {
    if (marketFilter !== "ALL" && c.market !== marketFilter) return false;
    if (themeOnly && !inTheme(c)) return false;
    if (heatingOnly && !heating.has(`${c.market}:${c.symbol}`)) return false;
    if (activePreset && !activePreset.test(c)) return false;
    if (regimeFilter !== "ALL" && c.regime_fit !== regimeFilter) return false;
    if (newOnly && c.is_new !== true) return false;
    if (cheapOnly && c.valuation_tier !== "싼 편") return false;
    if (growingOnly && c.growth_tier !== "성장") return false;
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      const haystack = `${c.symbol} ${c.name ?? ""}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });

  // 숫자 필터: [지표값, 기준, 방향]. 기준이 비어 있으면 그 필터는 꺼진 것.
  const num = (v: string) => (v.trim() === "" || !Number.isFinite(Number(v)) ? null : Number(v));
  const numChecks: [(c: Candidate) => number | null | undefined, number | null, "min" | "max"][] = [
    [(c) => c.piotroski, num(numFilter.minF), "min"],
    [(c) => c.debt_ratio, num(numFilter.maxDebt), "max"],
    [(c) => c.interest_coverage, num(numFilter.minInterest), "min"],
    [(c) => c.psr, num(numFilter.maxPsr), "max"],
    [(c) => c.per, num(numFilter.maxPer), "max"],
    [(c) => c.revenue_cagr_3y, num(numFilter.minCagr) == null ? null : num(numFilter.minCagr)! / 100, "min"],
  ];
  const activeChecks = numChecks.filter(([, lim]) => lim != null);
  let missingDropped = 0;
  const numFiltered = activeChecks.length === 0 ? filtered : filtered.filter((c) => {
    let missing = false;
    for (const [get, lim, dir] of activeChecks) {
      const v = get(c);
      if (v == null) { missing = true; continue; }
      if (dir === "min" ? v < lim! : v > lim!) return false;
    }
    if (missing) { missingDropped++; return false; }
    return true;
  });

  // 정렬: 값 없는 종목은 방향과 관계없이 맨 아래. 시가총액은 통화가 달라 '전체'에서는 시장별로 묶어 정렬.
  const sorted = sort == null ? numFiltered : [...numFiltered].sort((a, b) => {
    if (sort.key === "market_cap" && marketFilter === "ALL" && a.market !== b.market) return a.market.localeCompare(b.market);
    const va = a[sort.key] ?? null, vb = b[sort.key] ?? null;
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    return sort.dir === "asc" ? (va as number) - (vb as number) : (vb as number) - (va as number);
  });
  const onSort = (key: SortKey) => setSort((cur) =>
    cur?.key !== key ? { key, dir: SORT_FIRST_DIR[key] }
      : cur.dir === SORT_FIRST_DIR[key] ? { key, dir: cur.dir === "asc" ? "desc" : "asc" }
      : null);   // 세 번째 누르면 정렬 해제(원래 순서)

  // 후보가 275종목이라 목록만으로는 이번 주에 뭐가 달라졌는지 안 보인다.
  // 순위를 만들지 않으면서 "먼저 볼 것"을 주는 방법 - 이번 회차 신규만 따로 센다.
  const newCount = candidates.filter((c) => c.is_new === true).length;
  const newKnown = candidates.some((c) => c.is_new !== null && c.is_new !== undefined);

  // "탄탄한데 싸기도 한 것" - 이 목록은 이미 재무 필터를 통과한 종목만 있으니,
  // 밸류 하위 1/3을 걸면 그게 바로 새 아이디어를 찾기 시작할 자리가 된다.
  // 밸류 컬럼이 아직 채워지지 않았으면(스크립트 미실행) 버튼을 아예 숨긴다.
  const cheapCount = candidates.filter((c) => c.valuation_tier === "싼 편").length;
  const tierKnown = candidates.some((c) => c.valuation_tier != null);

  // 함정 필터가 못 거르는 것 - 무차입 흑자인데 매출이 3년째 주는 기업. "싼 편만"과
  // 나란히 둬야 그 조합(싸면서 안 자라는 것)이 눈에 보인다(SPEC_watchlist_growth.md).
  const growingCount = candidates.filter((c) => c.growth_tier === "성장").length;
  const growthKnown = candidates.some((c) => c.growth_tier != null);

  const statStyle: React.CSSProperties = {
    background: INSET_BG, border: `1px solid ${BORDER}`,
    padding: "10px 16px", textAlign: "center",
  };

  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "0 0 24px", color: TEXT_PRIMARY, background: PAGE_BG, minHeight: "100vh", fontFamily: MONO }}>
      {/* 팝업들 */}
      {selected && (
        <DetailModal
          c={selected}
          peer={peerStats[peerKey(selected)]}
          inList={addedSymbols.has(`${selected.market}:${selected.symbol}`)}
          note={myList.find((w) => w.market === selected.market && w.symbol === selected.symbol)?.note ?? null}
          onAdd={() => addToWatchlist(selected)}
          onSaveNote={(note) => saveNoteFromModal(selected, note)}
          onClose={() => { setSelected(null); clearStockParam(); }}
        />
      )}
      {linkMiss && (
        <div style={{ background: INSET_BG, border: `1px solid ${BORDER_CTRL}`, padding: "10px 14px", margin: "8px 0", fontSize: 13, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ color: TEXT_PRIMARY, fontWeight: 700 }}>{linkMiss.name || linkMiss.symbol}</span>
          <span style={{ color: TEXT_SECONDARY }}>
            이번 주 워치리스트 후보가 아닙니다(재무 필터 미통과 또는 대상 밖){linkMiss.mine ? " · 내 관심 목록에 있습니다" : ""}
          </span>
          <a href={externalQuoteUrl(linkMiss.market, linkMiss.symbol)} target="_blank" rel="noreferrer"
            style={{ color: "#ffb020" }}>{linkMiss.market === "KR" ? "네이버 금융" : "Yahoo Finance"}에서 보기 ↗</a>
          <button onClick={() => { setLinkMiss(null); clearStockParam(); }} style={{ marginLeft: "auto", color: TEXT_MUTED }} aria-label="닫기">✕</button>
          <MissDetail market={linkMiss.market} symbol={linkMiss.symbol} />
        </div>
      )}
      {infoKey && (
        <InfoModal info={INDICATOR_INFO[infoKey]} onClose={() => setInfoKey(null)} />
      )}

      {/* 헤더 */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, letterSpacing: "-0.01em", color: TEXT_PRIMARY }}>워치리스트</h1>
          {!loading && <AsOf date={screened_at} cadence="매주 월요일 아침" staleDays={8} />}
        </div>
        <p style={{ color: TEXT_MUTED, fontSize: 13, marginTop: 4 }}>
          재무 건전성 필터(함정 필터) 통과 종목 전부, 순위 없이 리스트업
        </p>
      </div>

      {/* 통계 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 12, marginBottom: 24 }}>
        {[
          { label: "후보 종목", value: candidates.length, highlight: false },
          // 이번 회차 신규는 275개 중 먼저 볼 것을 고르는 유일한 단서라 강조한다.
          // 직전 회차가 없으면 숫자 대신 "-"(알 수 없음) - 0으로 쓰면 "신규가 없다"는
          // 뜻이 되어 사실과 다르다.
          { label: "이번 회차 신규", value: newKnown ? newCount : "-", highlight: true },
          { label: "내 워치리스트", value: myList.length, highlight: false },
          { label: "성장 후보", value: candidates.filter((c) => c.regime_fit === "growth").length, highlight: false },
          { label: "배당 후보", value: candidates.filter((c) => c.regime_fit === "dividend").length, highlight: false },
        ].map(({ label, value, highlight }) => (
          <div key={label} style={{ ...statStyle, ...(highlight && newKnown && newCount > 0 ? { border: `1px solid ${GOOD}55` } : {}) }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: highlight && newKnown && newCount > 0 ? GOOD : ACCENT, fontVariantNumeric: "tabular-nums" }}>{value}</div>
            <div style={{ fontSize: 12, color: TEXT_MUTED, marginTop: 2 }}>{label}</div>
          </div>
        ))}
      </div>

      {/* 탭 */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, borderBottom: `1px solid ${BORDER}`, paddingBottom: 12 }}>
        {(["candidates", "my"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: tab === t ? ACCENT + "20" : "transparent",
            color: tab === t ? ACCENT : TEXT_MUTED,
            border: `1px solid ${tab === t ? ACCENT + "40" : BORDER_CTRL}`,
            padding: "6px 16px", fontSize: 13, cursor: "pointer",
          }}>
            {t === "candidates" ? `스크리닝 후보 (${sorted.length})` : `내 워치리스트 (${myList.length})`}
          </button>
        ))}
      </div>

      {/* ── 스크리닝 후보 탭 ── */}
      {tab === "candidates" && (
        <>
          {/* 검색 - 275종목 중 아는 티커/이름을 바로 찾는다. 다른 필터(신규만/싼 편만
              등)는 "뭘 볼지 모른 채 탐색"이 목적이라 켜고 끄는 토글이지만, 이건 찾는
              대상을 이미 알고 있는 반대 상황이라 텍스트 입력으로 둔다. */}
          <div style={{ position: "relative", marginBottom: 12, maxWidth: 320 }}>
            <Search size={14} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: TEXT_MUTED, pointerEvents: "none" }} />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="티커 또는 종목명 검색"
              style={{
                width: "100%", boxSizing: "border-box", padding: "7px 30px",
                fontSize: 13, fontFamily: MONO,
                background: INPUT_BG, color: TEXT_PRIMARY, border: `1px solid ${BORDER_CTRL}`,
                outline: "none",
              }}
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                aria-label="검색어 지우기"
                style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "transparent", border: "none", color: TEXT_MUTED, cursor: "pointer", padding: 2, display: "flex" }}
              >
                <X size={14} />
              </button>
            )}
          </div>

          {/* 좁혀 보기: 테마 흐름 교집합 + 조합 보기. 숫자는 현재 시장 범위 기준 */}
          {(themesKnown || tierKnown || growthKnown || heating.size > 0) && (
            <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: 12, color: TEXT_SECONDARY, marginRight: 2 }}>좁혀 보기</span>
              {themesKnown && (
                <button onClick={() => setThemeOnly((v) => !v)}
                  title={flowMode === "any"
                    ? "흐름 테마가 없어, 어느 테마에든 사업 소속(직접·부분)인 종목을 보여 줍니다."
                    : flowMode === "interim"
                      ? "라벨이 아직 없어(뉴스 기준선 쌓는 중) 실적 ↑인데 주가는 ↑ 아닌 테마에 사업 소속인 종목을 보여 줍니다."
                      : "레이더 Quiet 단계(Quiet Strength·Recovery) 또는 분기 '조용한 변화' 테마에 사업 소속인 종목"}
                  style={{
                    background: themeOnly ? ACCENT + "20" : "transparent",
                    color: themeOnly ? ACCENT : TEXT_MUTED,
                    border: `1px solid ${themeOnly ? ACCENT + "50" : BORDER_CTRL}`,
                    padding: "4px 12px", fontSize: 12, cursor: "pointer",
                  }}>{flowMode === "any" ? "테마 소속만" : flowMode === "interim" ? "실적 먼저 움직인 테마만" : "테마 흐름과 겹치는 종목만"} ({themeCount})</button>
              )}
              {heating.size > 0 && (
                <button onClick={() => setHeatingOnly((v) => !v)}
                  title="최근 주간 갱신에서 시장 관심도(뉴스량 기준 HOT/WARM/COLD)가 오른 종목. 보조 정보일 뿐 핵심 지표가 아닙니다."
                  style={{
                    background: heatingOnly ? ACCENT + "20" : "transparent",
                    color: heatingOnly ? ACCENT : TEXT_MUTED,
                    border: `1px solid ${heatingOnly ? ACCENT + "50" : BORDER_CTRL}`,
                    padding: "4px 12px", fontSize: 12, cursor: "pointer",
                  }}>관심도 오른 종목만 ({heatingCount})</button>
              )}
              {PRESETS.filter((p) => (p.key === "new_growth" ? newKnown : tierKnown) && growthKnown).map((p) => (
                <button key={p.key} title={p.note}
                  onClick={() => setPreset((cur) => (cur === p.key ? null : p.key))}
                  style={{
                    background: preset === p.key ? ACCENT + "20" : "transparent",
                    color: preset === p.key ? ACCENT : TEXT_MUTED,
                    border: `1px solid ${preset === p.key ? ACCENT + "50" : BORDER_CTRL}`,
                    padding: "4px 12px", fontSize: 12, cursor: "pointer",
                  }}>{p.label} ({presetCounts[p.key]})</button>
              ))}
            </div>
          )}
          {themeOnly && flowMode !== "label" && (
            <div style={{ fontSize: 12, color: TEXT_SECONDARY, marginBottom: 10 }}>
              {flowMode === "interim"
                ? <>라벨이 아직 없어(뉴스 기준선이 쌓이는 중) <b style={{ color: TEXT_PRIMARY }}>실적 ↑인데 주가는 → 또는 ↓인 테마</b>에 사업 소속인 종목을 보여 줍니다. Quiet 라벨 조건에서 뉴스만 뺀 임시 기준입니다.</>
                : <>지금은 흐름 테마가 없어 어느 테마에든 사업 소속인 종목으로 대신 보여 줍니다.</>}
            </div>
          )}
          {activePreset && (
            <div style={{ fontSize: 12, color: TEXT_SECONDARY, marginBottom: 10 }}>
              조합 보기: {activePreset.label} - {activePreset.note}
            </div>
          )}

          <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
            {(["ALL", "US", "KR"] as const).map((m) => (
              <button key={m} onClick={() => setMarketFilter(m)} style={{
                background: marketFilter === m ? INFO + "20" : "transparent",
                color: marketFilter === m ? INFO : TEXT_MUTED,
                border: `1px solid ${marketFilter === m ? INFO + "40" : BORDER_CTRL}`,
                padding: "4px 12px", fontSize: 12, cursor: "pointer",
              }}>{m === "ALL" ? "전체" : m}</button>
            ))}
            {newKnown && newCount > 0 && (
              <>
                <div style={{ width: 1, background: BORDER_CTRL, margin: "0 4px" }} />
                <button onClick={() => setNewOnly((v) => !v)} style={{
                  background: newOnly ? GOOD + "20" : "transparent",
                  color: newOnly ? GOOD : TEXT_MUTED,
                  border: `1px solid ${newOnly ? GOOD + "40" : BORDER_CTRL}`,
                  padding: "4px 12px", fontSize: 12, cursor: "pointer",
                }}>이번 회차 신규만 ({newCount})</button>
              </>
            )}
            {tierKnown && (
              <>
                <div style={{ width: 1, background: BORDER_CTRL, margin: "0 4px" }} />
                <button onClick={() => setCheapOnly((v) => !v)} style={{
                  background: cheapOnly ? GOOD + "20" : "transparent",
                  color: cheapOnly ? GOOD : TEXT_MUTED,
                  border: `1px solid ${cheapOnly ? GOOD + "40" : BORDER_CTRL}`,
                  padding: "4px 12px", fontSize: 12, cursor: "pointer",
                }}>싼 편만 ({cheapCount})</button>
              </>
            )}
            {growthKnown && (
              <>
                <div style={{ width: 1, background: BORDER_CTRL, margin: "0 4px" }} />
                <button onClick={() => setGrowingOnly((v) => !v)} style={{
                  background: growingOnly ? GOOD + "20" : "transparent",
                  color: growingOnly ? GOOD : TEXT_MUTED,
                  border: `1px solid ${growingOnly ? GOOD + "40" : BORDER_CTRL}`,
                  padding: "4px 12px", fontSize: 12, cursor: "pointer",
                }}>성장만 ({growingCount})</button>
              </>
            )}
            <div style={{ width: 1, background: BORDER_CTRL, margin: "0 4px" }} />
            {(["ALL", "growth", "dividend", "neutral"] as const).map((r) => (
              <button key={r} onClick={() => setRegimeFilter(r)} style={{
                background: regimeFilter === r ? INFO + "20" : "transparent",
                color: regimeFilter === r ? INFO : TEXT_MUTED,
                border: `1px solid ${regimeFilter === r ? INFO + "40" : BORDER_CTRL}`,
                padding: "4px 12px", fontSize: 12, cursor: "pointer",
              }}>{r === "ALL" ? "전체" : r === "growth" ? "성장" : r === "dividend" ? "배당" : "중립"}</button>
            ))}
          </div>

          {/* 지표 숫자 필터 - 접어 두고 필요할 때 연다 */}
          <div style={{ marginBottom: 16 }}>
            <button onClick={() => setShowNumFilter((v) => !v)} style={{
              background: activeChecks.length ? ACCENT + "18" : "transparent",
              color: activeChecks.length ? ACCENT : TEXT_SECONDARY,
              border: `1px solid ${activeChecks.length ? ACCENT + "40" : BORDER_CTRL}`,
              padding: "4px 12px", fontSize: 12, cursor: "pointer",
            }}>
              {showNumFilter ? "▾" : "▸"} 지표 필터{activeChecks.length ? ` (${activeChecks.length}개 적용)` : ""}
            </button>
            {sort && (
              <span style={{ marginLeft: 10, fontSize: 12, color: TEXT_SECONDARY }}>
                정렬: {SORT_LABEL[sort.key]} {sort.dir === "asc" ? "낮은 순" : "높은 순"}
                <button onClick={() => setSort(null)} style={{ marginLeft: 6, background: "transparent", border: "none", color: TEXT_MUTED, cursor: "pointer", fontSize: 12 }}>해제 ✕</button>
              </span>
            )}
            {showNumFilter && (
              <div style={{ marginTop: 10, padding: "12px 14px", background: INSET_BG, border: `1px solid ${BORDER}`, display: "flex", flexWrap: "wrap", gap: "10px 18px", alignItems: "center" }}>
                {([
                  ["minF", "F-Score", "이상", "예: 7"],
                  ["maxDebt", "부채비율(%)", "이하", "예: 100"],
                  ["minInterest", "이자보상(배)", "이상", "예: 5"],
                  ["maxPsr", "PSR", "이하", "예: 2"],
                  ["maxPer", "PER", "이하", "예: 15"],
                  ["minCagr", "매출 3년 성장(%)", "이상", "예: 10"],
                ] as const).map(([k, label, dir, ph]) => (
                  <label key={k} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: TEXT_SECONDARY }}>
                    {label}
                    <input value={numFilter[k]} onChange={(e) => setNumFilter((f) => ({ ...f, [k]: e.target.value }))}
                      inputMode="decimal" placeholder={ph}
                      style={{ width: 64, padding: "4px 6px", fontSize: 12, fontFamily: MONO, background: INPUT_BG, color: TEXT_PRIMARY, border: `1px solid ${BORDER_CTRL}`, outline: "none" }} />
                    <span style={{ color: TEXT_MUTED }}>{dir}</span>
                  </label>
                ))}
                {activeChecks.length > 0 && (
                  <button onClick={() => setNumFilter({ minF: "", maxDebt: "", minInterest: "", maxPsr: "", maxPer: "", minCagr: "" })}
                    style={{ background: "transparent", border: `1px solid ${BORDER_CTRL}`, color: TEXT_SECONDARY, padding: "3px 10px", fontSize: 12, cursor: "pointer" }}>
                    모두 지우기
                  </button>
                )}
                {missingDropped > 0 && (
                  <span style={{ fontSize: 12, color: TEXT_MUTED, flexBasis: "100%" }}>
                    값이 없어(계산 불가) 빠진 종목 {missingDropped}개 - 탈락이 아니라 확인할 수 없는 것입니다.
                  </span>
                )}
              </div>
            )}
          </div>

          {loading ? (
            <div style={{ color: TEXT_MUTED, textAlign: "center", padding: 60 }}>불러오는 중...</div>
          ) : sorted.length === 0 ? (
            <div style={{ color: TEXT_MUTED, textAlign: "center", padding: 60 }}>
              {candidates.length === 0
                ? "스크리닝 데이터 없음."
                : searchQuery.trim()
                  ? "일치하는 종목 없음 - 함정 필터 통과 후보 275종목 중에만 검색합니다."
                  : "필터 조건에 맞는 종목 없음."}
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <p style={{ fontSize: 12, color: TEXT_MUTED, marginBottom: 8 }}>행 클릭 시 상세 정보 · 열 제목 클릭 시 정렬 · ⓘ 클릭 시 지표 설명<span className="sm:hidden"> · 좁은 화면에선 시총·부채·이자보상·체제·추가 열을 숨김(행을 누르면 상세에 전부)</span></p>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${BORDER}` }}>
                    {/* 15열 -> 9열(2026-10-04): 마켓·티커·종목명·섹터를 한 칸에, 밸류 배지+PSR/PER, 성장 배지+3년/1년을
                        각각 한 칸에 합쳤다. 현재가는 상세 화면에 있다. 가로 스크롤 없이 한 화면에 들어오게. */}
                    <ColHeader label="종목" />
                    <ColHeader label="시가총액" sortKey="market_cap" sort={sort} onSort={onSort} className="hidden sm:table-cell" />
                    <ColHeader label="F-Score" infoKey="fscore" onInfo={setInfoKey} sortKey="piotroski" sort={sort} onSort={onSort} />
                    <ColHeader label="부채비율" infoKey="debt" onInfo={setInfoKey} sortKey="debt_ratio" sort={sort} onSort={onSort} className="hidden sm:table-cell" />
                    <ColHeader label="이자보상" infoKey="interest" onInfo={setInfoKey} sortKey="interest_coverage" sort={sort} onSort={onSort} className="hidden sm:table-cell" />
                    <ColHeader label="밸류 · PSR" infoKey="valuation" onInfo={setInfoKey} sortKey="psr" sort={sort} onSort={onSort} />
                    <ColHeader label="성장 · 3년" infoKey="growth" onInfo={setInfoKey} sortKey="revenue_cagr_3y" sort={sort} onSort={onSort} />
                    <ColHeader label="체제" infoKey="regime" onInfo={setInfoKey} className="hidden sm:table-cell" />
                    <th className="hidden sm:table-cell" style={{ padding: "8px 8px" }} />
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((c) => {
                    const key = `${c.market}:${c.symbol}`;
                    const inList = addedSymbols.has(key);
                    return (
                      <tr key={key}
                        onClick={() => setSelected(c)}
                        style={{ borderBottom: `1px solid ${BORDER}`, cursor: "pointer" }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = HOVER_BG)}
                        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                      >
                        <td style={{ padding: "8px 8px", minWidth: 120, maxWidth: 220 }}>
                          {/* 배지(신규·내 관심·실적 반전 등)가 많으면 다음 줄로 - 좁은 화면에서 이 칸이 표를 밀어내지 않게 */}
                          <div style={{ display: "flex", alignItems: "center", gap: 6, whiteSpace: "nowrap", flexWrap: "wrap", rowGap: 3 }}>
                            <span style={{ color: c.market === "US" ? INFO : BAD, fontSize: 11, fontWeight: 600 }}>{c.market}</span>
                            <span style={{ fontWeight: 700, color: NUM }}>{c.symbol}</span>
                            {c.is_new === true && (
                              <span
                                // first_seen은 이력 기록이 쌓이기 시작한 뒤로만 알 수 있다 - 실제
                                // 첫 통과일이 그보다 이전일 수 있어 "최초"라고 단정하지 않는다.
                                title={c.is_reentry
                                  ? `예전에 후보였다가 빠진 뒤 이번에 다시 통과 (기록상 최초 등장: ${c.first_seen ?? "-"})`
                                  : "이번 회차에 처음 필터를 통과 (이력 기록 시작 이후 처음)"}
                                style={{
                                  marginLeft: 6, fontSize: 10, fontWeight: 700,
                                  color: GOOD, border: `1px solid ${GOOD}55`,
                                  padding: "1px 5px", verticalAlign: "middle",
                                }}>
                                {c.is_reentry ? "재진입" : "신규"}
                              </span>
                            )}
                            {(inList || isTurnaround(c)) && (
                              <TagBadges tags={[...(inList ? ["my"] : []), ...(isTurnaround(c) ? ["turnaround"] : [])]} />
                            )}
                            {heating.has(key) && (
                              <span title={`최근 주간 갱신에서 관심도 상승 (${heating.get(key)}) · 뉴스량 기준 보조 정보`}
                                style={{ fontSize: 10, fontWeight: 700, color: BAD, border: `1px solid ${BAD}55`, padding: "1px 5px", verticalAlign: "middle" }}>
                                ▲관심
                              </span>
                            )}
                          </div>
                          <div style={{ color: TEXT_SECONDARY, fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {c.name ?? "-"}{c.sector ? <span style={{ color: TEXT_MUTED }}> · {c.sector}</span> : null}
                          </div>
                          {(c.themes ?? []).length > 0 && (
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 3 }}>
                              {(c.themes ?? []).slice(0, 3).map((t) => (
                                <span key={t.theme_id}
                                  title={[t.label && `레이더: ${t.label}`, t.quarterly && `분기: ${t.quarterly}`,
                                          `실적 ${arrowText(t.earn_arrow)} · 주가 ${arrowText(t.price_arrow)}`].filter(Boolean).join(" · ")}
                                  style={{
                                    fontSize: 10, padding: "0 5px", whiteSpace: "nowrap",
                                    color: flowTest?.(t) ? ACCENT : TEXT_MUTED,
                                    border: `1px solid ${flowTest?.(t) ? ACCENT + "60" : BORDER_CTRL}`,
                                  }}>{themeName(t.theme_id).ko}</span>
                              ))}
                              {(c.themes ?? []).length > 3 && <span style={{ fontSize: 10, color: TEXT_MUTED }}>+{(c.themes ?? []).length - 3}</span>}
                            </div>
                          )}
                        </td>
                        <td className="hidden sm:table-cell" style={{ padding: "8px 8px", color: NUM, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{formatCap(c.market, c.market_cap)}</td>
                        <td style={{ padding: "8px 8px" }}><PiotroskiBadge score={c.piotroski} /></td>
                        <td className="hidden sm:table-cell" style={{ padding: "8px 8px", whiteSpace: "nowrap" }}>
                          <MetricOrNote value={c.debt_ratio} note={c.data_notes?.debt} format={(v) => `${v}%`} />
                        </td>
                        <td className="hidden sm:table-cell" style={{ padding: "8px 8px", whiteSpace: "nowrap" }}>
                          <MetricOrNote value={c.interest_coverage} note={c.data_notes?.interest} format={(v) => v.toFixed(1) + "x"} />
                        </td>
                        <td style={{ padding: "8px 8px" }}>
                          <div><ValuationBadge tier={c.valuation_tier} /></div>
                          <div style={{ marginTop: 2 }}><ValuationNumbers psr={c.psr} per={c.per} /></div>
                        </td>
                        <td style={{ padding: "8px 8px" }}>
                          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                            <GrowthBadge tier={c.growth_tier} prefix={c.rev_q_tier || c.rev_ttm_tier ? "3년" : undefined} title="연간 매출 3년 CAGR 기준" />
                            {/* 지금 흐름: 최근 4개 분기 합 비교가 있으면 그것(덜 흔들림), 없으면 최근 한 분기 비교 */}
                            {c.rev_ttm_tier
                              ? <GrowthBadge tier={c.rev_ttm_tier} prefix="1년"
                                  title={`최근 4개 분기 매출 합, 그 전 4개 분기 대비 ${fmtGrowthPct(c.rev_ttm_yoy)} (최근 분기 단독 ${fmtGrowthPct(c.rev_q_yoy)})`} />
                              : <GrowthBadge tier={c.rev_q_tier} prefix="분기"
                                  title={`${quarterLabel(c.rev_q_quarter)} 매출, 1년 전 같은 분기 대비 ${fmtGrowthPct(c.rev_q_yoy)}`} />}
                          </div>
                          <div style={{ marginTop: 2 }}><GrowthNumbers cagr3y={c.revenue_cagr_3y} yoy={c.revenue_yoy} /></div>
                          {(c.op_margin_q_status === "개선" || c.op_margin_q_status === "악화") && (
                            <div style={{ marginTop: 2, fontSize: 11, color: c.op_margin_q_status === "개선" ? GOOD : CAUTION, whiteSpace: "nowrap" }}
                              title={`최근 분기 영업이익률 ${c.op_margin_q_now != null ? (c.op_margin_q_now * 100).toFixed(1) + "%" : "-"}, 1년 전 같은 분기 대비 ${c.op_margin_q_change != null ? ((c.op_margin_q_change >= 0 ? "+" : "") + (c.op_margin_q_change * 100).toFixed(1)) : "-"}%p`}>
                              분기 이익률 {c.op_margin_q_status === "개선" ? "↑" : "↓"}
                            </div>
                          )}
                        </td>
                        <td className="hidden sm:table-cell" style={{ padding: "8px 8px" }}><RegimeBadge fit={c.regime_fit} /></td>
                        <td className="hidden sm:table-cell" style={{ padding: "8px 8px" }} onClick={(e) => e.stopPropagation()}>
                          <button
                            onClick={() => !inList && addToWatchlist(c)}
                            disabled={inList}
                            style={{
                              background: inList ? PANEL_BG : ACCENT + "20",
                              color: inList ? TEXT_FAINT : ACCENT,
                              border: `1px solid ${inList ? BORDER : ACCENT + "40"}`,
                              padding: "3px 10px", fontSize: 11,
                              cursor: inList ? "default" : "pointer",
                            }}>
                            {inList ? "추가됨" : "+ 추가"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── 내 워치리스트 탭 ── */}
      {tab === "my" && (
        myList.length === 0 ? (
          <div style={{ color: TEXT_MUTED, textAlign: "center", padding: 60 }}>아직 추가한 종목이 없어요.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {myList.map((item) => (
              <div key={item.id} style={{ background: INSET_BG, border: `1px solid ${BORDER}`, padding: "12px 16px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ color: item.market === "US" ? INFO : BAD, fontSize: 11, fontWeight: 600, minWidth: 24 }}>{item.market}</span>
                  <span style={{ fontWeight: 700, fontSize: 15, minWidth: 60, color: NUM }}>{item.symbol}</span>
                  {heating.has(`${item.market}:${item.symbol}`) && (
                    <span title={`최근 주간 갱신에서 관심도 상승 (${heating.get(`${item.market}:${item.symbol}`)}) · 뉴스량 기준 보조 정보`}
                      style={{ fontSize: 10, fontWeight: 700, color: BAD, border: `1px solid ${BAD}55`, padding: "1px 5px", verticalAlign: "middle" }}>
                      ▲관심
                    </span>
                  )}
                  <span style={{ color: TEXT_SECONDARY, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.name ?? ""}</span>
                  <span style={{ color: TEXT_FAINT, fontSize: 11 }}>{item.added_at.slice(0, 10)}</span>
                  <button onClick={() => removeFromWatchlist(item.id)} style={{ background: "transparent", color: TEXT_MUTED, border: `1px solid ${BORDER_CTRL}`, padding: "2px 8px", fontSize: 11, cursor: "pointer" }}>삭제</button>
                </div>
                {/* 메모 */}
                <div style={{ marginTop: 8 }}>
                  {editingNote === item.id ? (
                    <div style={{ display: "flex", gap: 6 }}>
                      <input
                        value={noteDraft}
                        onChange={(e) => setNoteDraft(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") saveNote(item); if (e.key === "Escape") setEditingNote(null); }}
                        placeholder="담은 이유, 지켜볼 포인트… (예: AI 전력 수요 수혜, 2분기 실적 확인)"
                        autoFocus
                        style={{ flex: 1, background: INPUT_BG, color: TEXT_PRIMARY, border: `1px solid ${BORDER_CTRL}`, padding: "6px 10px", fontSize: 12, outline: "none" }}
                      />
                      <button onClick={() => saveNote(item)} style={{ background: ACCENT + "18", color: ACCENT, border: `1px solid ${ACCENT}33`, padding: "4px 12px", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>저장</button>
                      <button onClick={() => setEditingNote(null)} style={{ background: PANEL_BG, color: TEXT_MUTED, border: `1px solid ${BORDER_CTRL}`, padding: "4px 10px", fontSize: 12, cursor: "pointer" }}>취소</button>
                    </div>
                  ) : (
                    <button
                      onClick={() => { setEditingNote(item.id); setNoteDraft(item.note ?? ""); }}
                      style={{ display: "flex", alignItems: "center", gap: 6, background: "transparent", border: "none", cursor: "pointer", padding: 0, textAlign: "left" }}
                    >
                      <Pencil size={11} style={{ color: TEXT_FAINT, flexShrink: 0 }} />
                      <span style={{ color: item.note ? TEXT_SECONDARY : TEXT_FAINT, fontSize: 12 }}>
                        {item.note || "메모 추가 — 왜 담았는지 기록해두세요"}
                      </span>
                    </button>
                  )}
                </div>

                {/* 보유 기록 — 실제로 산 종목만 적으면 된다. 안 적으면 그냥 관심 목록.
                    분기 점검 때 "적어둔 깨지는 조건이 현실이 됐나"를 묻는 게 목적이라
                    수익률·순위는 계산하지 않는다(투자 실행 가이드 4단계). */}
                <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${BORDER}` }}>
                  {editingHolding === item.id ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <input
                          value={holdDraft.bought_at}
                          onChange={(e) => setHoldDraft((d) => ({ ...d, bought_at: e.target.value }))}
                          placeholder="매수일 2026-10-02"
                          style={{ width: 150, background: INPUT_BG, color: TEXT_PRIMARY, border: `1px solid ${BORDER_CTRL}`, padding: "5px 8px", fontSize: 12, outline: "none", fontFamily: MONO }}
                        />
                        <input
                          value={holdDraft.buy_price}
                          onChange={(e) => setHoldDraft((d) => ({ ...d, buy_price: e.target.value }))}
                          placeholder={item.market === "KR" ? "매수가 12300" : "매수가 45.20"}
                          inputMode="decimal"
                          style={{ width: 150, background: INPUT_BG, color: TEXT_PRIMARY, border: `1px solid ${BORDER_CTRL}`, padding: "5px 8px", fontSize: 12, outline: "none", fontFamily: MONO }}
                        />
                      </div>
                      <input
                        value={holdDraft.thesis_breaks}
                        onChange={(e) => setHoldDraft((d) => ({ ...d, thesis_breaks: e.target.value }))}
                        onKeyDown={(e) => { if (e.key === "Enter") saveHolding(item); if (e.key === "Escape") setEditingHolding(null); }}
                        placeholder="깨지는 조건 — 이게 사실이 되면 내 판단이 틀린 것 (예: 주 고객사 설비투자 축소 / 영업이익률 2분기 연속 하락)"
                        style={{ width: "100%", boxSizing: "border-box", background: INPUT_BG, color: TEXT_PRIMARY, border: `1px solid ${BORDER_CTRL}`, padding: "5px 8px", fontSize: 12, outline: "none" }}
                      />
                      <div style={{ display: "flex", gap: 6 }}>
                        <button onClick={() => saveHolding(item)} style={{ background: ACCENT + "18", color: ACCENT, border: `1px solid ${ACCENT}33`, padding: "4px 12px", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>저장</button>
                        <button onClick={() => setEditingHolding(null)} style={{ background: PANEL_BG, color: TEXT_MUTED, border: `1px solid ${BORDER_CTRL}`, padding: "4px 10px", fontSize: 12, cursor: "pointer" }}>취소</button>
                      </div>
                    </div>
                  ) : (
                    <button
                      onClick={() => startEditHolding(item)}
                      style={{ display: "flex", alignItems: "center", gap: 8, background: "transparent", border: "none", cursor: "pointer", padding: 0, textAlign: "left", flexWrap: "wrap" }}
                    >
                      {item.bought_at || item.buy_price != null || item.thesis_breaks ? (
                        <>
                          <span style={{ fontSize: 11, color: GOOD, border: `1px solid ${GOOD}44`, background: GOOD + "18", padding: "1px 6px" }}>보유</span>
                          <span style={{ fontSize: 12, color: TEXT_SECONDARY, fontVariantNumeric: "tabular-nums" }}>
                            {item.bought_at ?? "-"} · {item.buy_price != null ? formatPrice(item.market, item.buy_price) : "-"}
                          </span>
                          {item.thesis_breaks && (
                            <span style={{ fontSize: 12, color: CAUTION }}>깨지는 조건: {item.thesis_breaks}</span>
                          )}
                        </>
                      ) : (
                        <>
                          <Pencil size={11} style={{ color: TEXT_FAINT, flexShrink: 0 }} />
                          <span style={{ color: TEXT_FAINT, fontSize: 12 }}>
                            보유 기록 추가 — 실제로 샀다면 매수일·매수가·깨지는 조건
                          </span>
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}
