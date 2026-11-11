"use client";

// 종목 하나에 대한 섹션(2026-11-05 워치리스트 상세 팝업에서 떼어 냄) - 워치리스트 팝업과 기업 카드(/company)가 같이 쓴다.
// 모두 시장·종목코드만으로 자기 API를 불러 그린다. 색은 워치리스트 화면과 같은 값.
import { useEffect, useState } from "react";
import { INVESTOR_BY_ID, STYLE_META, investorFull, quarterLabel as q13f, usd } from "@/src/lib/institutions";
import { themeName } from "@/src/lib/themeNames";

export type StockRef = { market: string; symbol: string };

const PANEL_BG  = "#111009";
const INSET_BG  = "#0e0d08";
const BORDER    = "#262112";
const BORDER_CTRL = "#453b1f";
const TEXT_BODY      = "#d6d0c0";
const TEXT_SECONDARY = "#bcb4a2";
const TEXT_MUTED     = "#8b8271";
const TEXT_FAINT     = "#736b57";
const ACCENT  = "#ffb020";
const GOOD    = "#4ade80";
const WARN    = "#facc15";
const BAD     = "#f87171";
const INFO    = "#6fb3b8";

interface NarrativeBrief {
  sentiment: "HOT" | "WARM" | "COLD";
  sources: string[];
  cached_at: string;
  prev_sentiment?: "HOT" | "WARM" | "COLD" | null;
  trend?: "up" | "down" | "flat" | null;
}

// ── 뉴스 관심도 (2026-11-11) ────────────────────────────────────────────────
// 주간 파이프라인(generate_narratives.py)이 최근 1주 뉴스 헤드라인을 GPT로 HOT/WARM/COLD로 나눈 것만 보여 준다.
// 같은 결과에 있던 스토리·촉매·리스크 문장은 회사가 달라도 거의 같은 상투적 문장(경쟁 심화·규제 강화·…)과
// 앞날 짐작('지속될 가능성이 높다')이라 뺐다 - 회사 소개·테마 근거·숫자·반대 의견 기사가 같은 화면에 있다.
// 관심도는 브리핑 '관심도 상승'·신호 기록(sentiment_heating)이 쓰고 있어 남긴다. 판정 아님.
const SENTIMENT_STYLE: Record<string, { label: string; color: string; emoji: string }> = {
  HOT:  { label: "시장 관심 높음", color: BAD, emoji: "🔥" },
  WARM: { label: "꾸준한 관심",    color: WARN, emoji: "🌤" },
  COLD: { label: "시장 관심 밖",   color: INFO, emoji: "❄️" },
};

export function NarrativeSection({ c }: { c: StockRef }) {
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
        if (data.pending) { setPending(true); return; }
        if (!res.ok) throw new Error(data.error ?? "요청 실패");
        setBrief(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "관심도를 불러오지 못했습니다");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [c.market, c.symbol]);

  const sent = brief ? (SENTIMENT_STYLE[brief.sentiment] ?? SENTIMENT_STYLE.WARM) : null;

  return (
    <div className="p-3 space-y-2" style={{ background: INSET_BG, border: `1px solid ${BORDER}`, borderRadius: 10 }}>
      <p className="text-[12px] font-semibold" style={{ color: TEXT_SECONDARY }}>뉴스 관심도</p>
      {loading && <p className="text-[12px] animate-pulse" style={{ color: TEXT_SECONDARY }}>불러오는 중...</p>}
      {pending && !loading && (
        <p className="text-[12px]" style={{ color: TEXT_SECONDARY }}>
          아직 없습니다. 워치리스트 후보·내 워치리스트 종목만 주 1회(일요일 밤) 셉니다.
        </p>
      )}
      {error && !loading && <p className="text-[12px]" style={{ color: BAD }}>{error}</p>}
      {brief && sent && !loading && (
        <>
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
          </div>
          <p className="text-[12px] flex flex-wrap gap-x-1.5" style={{ color: TEXT_MUTED }}>
            <span>최근 1주 뉴스 헤드라인을 GPT가 세 단계로 나눈 것 · 판정 아님 · {brief.cached_at.slice(0, 10)} 갱신</span>
            {brief.sources.slice(0, 3).map((url, i) => (
              <a key={i} href={url} target="_blank" rel="noopener noreferrer" className="underline">기사{i + 1}</a>
            ))}
          </p>
        </>
      )}
    </div>
  );
}

// ── 종목 정성 체크리스트 (종목별 독립 저장) ──────────────────────────────────
interface ChecklistItem { id: string; text: string; checked: boolean }

// 내부자 장내 매수(2026-10-21) - 최근 180일 공시. 없으면 칸을 숨긴다. 금액은 공시 단가 × 주식 수.
interface InsiderTrade { filing_id: string; filed_on: string; trade_date: string | null; owner: string; role: string | null;
  shares: number | null; price: number | null; value: number | null; plan: number | boolean | null }
export function InsiderSection({ c }: { c: StockRef }) {
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
    <div className="p-3" style={{ background: INSET_BG, border: `1px solid ${BORDER}`, borderRadius: 10 }}>
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
      <p className="text-[12px] mt-1.5" style={{ color: TEXT_SECONDARY }}>
        {kr ? "DART 임원ㆍ주요주주 소유보고" : "SEC Form 4"} · 장내에서 직접 산 것만(스톡옵션·증여·장외 제외)
      </p>
    </div>
  );
}

// 미국 8-K 주요 공시(2026-10-21) - 최근 180일. 종류는 항목 번호, 아래 줄은 원문 첫머리(번역·요약 없음). 없으면 칸을 숨긴다.
interface Us8kFiling { accession: string; filed_on: string; url: string | null; warn: boolean;
  items: { item: string; label: string; warn: boolean; excerpt?: string | null }[] }
export function Us8kSection({ c }: { c: StockRef }) {
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
    <div className="p-3" style={{ background: INSET_BG, border: `1px solid ${BORDER}`, borderRadius: 10 }}>
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
      <p className="text-[12px] mt-1.5" style={{ color: TEXT_SECONDARY }}>
        SEC 8-K · 실적 발표만 있는 것은 뺌 · 임원 변동의 사임/선임은 원문 낱말로 나눈 것
      </p>
    </div>
  );
}

// 후보가 아닌 종목으로 들어왔을 때(브리핑 "관심 밖 내부자 매수" 등, 2026-10-21) - 재무 필터 판정과 사유, 내부자 장내 매수·8-K.
// 탈락이어도 왜 떨어졌는지가 정보다. 판정이 없으면 "미확인"(원칙 4).
// 필터 칩 묶음 - 앞에 작은 이름(시장·목록·밸류·성장·체제)

// ── 유명 투자자 13F (2026-10-25) ─────────────────────────────────────────────
// 사용자가 고른 운용사 15곳 중 이 종목을 가장 최근 분기 말에 들고 있던(또는 그 분기에 다 판) 곳. 미국 종목만(13F는 미국 상장주식).
const STATUS_KO: Record<string, string> = { new: "신규 매수", added: "추가 매수", reduced: "일부 매도", same: "변동 없음", sold: "전량 매도" };
export function InstitutionSection({ c }: { c: StockRef }) {
  const [holders, setHolders] = useState<{ manager_id: string; period: string; value: number; weight: number | null; status: string | null; share_chg: number | null; prev_value: number | null }[]>([]);
  useEffect(() => {
    if (c.market !== "US") return;
    let cancelled = false;
    fetch(`/api/investors?symbol=${encodeURIComponent(c.symbol)}`).then((r) => r.json())
      .then((d) => { if (!cancelled) setHolders(Array.isArray(d.holders) ? d.holders : []); })
      .catch(() => { if (!cancelled) setHolders([]); });
    return () => { cancelled = true; };
  }, [c.market, c.symbol]);
  if (c.market !== "US" || holders.length === 0) return null;
  const sorted = [...holders].sort((a, b) => (b.value || b.prev_value || 0) - (a.value || a.prev_value || 0));
  return (
    <div className="p-3" style={{ background: INSET_BG, border: `1px solid ${BORDER}`, borderRadius: 10 }}>
      <p className="text-[12px] font-semibold mb-1.5" style={{ color: TEXT_SECONDARY }}>
        유명 투자자 13F <span className="font-normal" style={{ color: TEXT_MUTED }}>— 고른 운용사 15곳 중 {holders.filter((h) => h.status !== "sold").length}곳 보유</span>
      </p>
      <div className="space-y-0.5">
        {sorted.map((h) => {
          const meta = INVESTOR_BY_ID[h.manager_id];
          const col = h.status === "new" || h.status === "added" ? GOOD : h.status === "sold" || h.status === "reduced" ? BAD : TEXT_SECONDARY;
          return (
            <p key={h.manager_id} className="text-[12px] flex flex-wrap gap-x-2" style={{ fontVariantNumeric: "tabular-nums" }}>
              <span className="text-white">{investorFull(meta) || h.manager_id}</span>
              {meta && <span style={{ color: STYLE_META[meta.style].color }}>{STYLE_META[meta.style].emoji} {meta.style}</span>}
              <span style={{ color: col }}>{h.status ? STATUS_KO[h.status] ?? h.status : "비교 없음"}
                {(h.status === "added" || h.status === "reduced") && h.share_chg != null ? ` ${h.share_chg >= 0 ? "+" : ""}${(h.share_chg * 100).toFixed(0)}%` : ""}</span>
              <span>{h.status === "sold" ? `직전 ${usd(h.prev_value)}` : usd(h.value)}</span>
              {h.weight != null && h.status !== "sold" && <span style={{ color: TEXT_MUTED }}>비중 {(h.weight * 100).toFixed(1)}%</span>}
              <span style={{ color: TEXT_FAINT }}>{q13f(h.period)} 말</span>
            </p>
          );
        })}
      </div>
      <p className="text-[12px] mt-1.5" style={{ color: TEXT_SECONDARY }}>
        SEC 13F · 분기 말 보유를 45일 안에 신고한 것(산 시점·가격 모름, 매수 보유만) · <a href="/investors" style={{ color: ACCENT }}>전체 보기</a>
      </p>
    </div>
  );
}

// ── 테마 동료 비교 (2026-10-25) ───────────────────────────────────────────────
// 이 종목이 사업 소속인 테마마다, 소속 기업들의 중앙값·가운데 절반(25~75%) 옆에 이 종목 값을 둔다(/api/radar/peers).
// 지표마다 따로 보여 줄 뿐 합치지 않고 순위도 매기지 않는다(원칙 1). 동료 값이 5곳 미만이면 비교하지 않는다(데이터 부족).
type PeerMetric = { self: number | null; n: number; median: number | null; q1: number | null; q3: number | null };
type PeerTheme = { theme_id: string; week: string | null; members: number; metrics: Record<string, PeerMetric> };
const PEER_ROWS: { key: string; label: string; fmt: (v: number) => string; hint: string }[] = [
  { key: "rev_yoy", label: "매출 YoY", fmt: (v) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(0)}%`, hint: "최근 분기 매출, 1년 전 같은 분기 대비" },
  { key: "om_now", label: "영업이익률", fmt: (v) => `${(v * 100).toFixed(1)}%`, hint: "최근 분기" },
  { key: "fcf_yield_3y", label: "FCF 수익률", fmt: (v) => `${(v * 100).toFixed(1)}%`, hint: "3년 평균 잉여현금흐름 / 시가총액, 금융업은 계산 안 함" },
  { key: "roe", label: "ROE", fmt: (v) => `${v.toFixed(1)}%`, hint: "재무 필터가 계산한 값" },
];
const PEER_GRID = "sm:grid-cols-[6rem_4.5rem_7.5rem_minmax(0,1fr)_9rem] gap-x-2";
function PeerBar({ m }: { m: PeerMetric }) {
  if (m.q1 == null || m.q3 == null || m.median == null) return null;
  const lo = Math.min(m.q1, m.self ?? m.q1), hi = Math.max(m.q3, m.self ?? m.q3);
  const pad = (hi - lo) * 0.15 || Math.abs(hi) * 0.1 || 1;
  const x = (v: number) => `${((v - (lo - pad)) / (hi - lo + 2 * pad)) * 100}%`;
  return (
    <div className="relative h-2.5 w-full min-w-[80px] rounded-full" style={{ background: "#1a1710" }} aria-hidden>
      <div className="absolute top-0 h-full rounded-full" style={{ left: x(m.q1), width: `calc(${x(m.q3)} - ${x(m.q1)})`, background: "#ffb02033" }} />
      <div className="absolute top-0 h-full w-px" style={{ left: x(m.median), background: TEXT_MUTED }} />
      {m.self != null && <div className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full" style={{ left: x(m.self), background: ACCENT }} />}
    </div>
  );
}
function peerWhere(m: PeerMetric): { text: string; color: string } {
  if (m.self == null) return { text: "이 종목 값 없음", color: TEXT_FAINT };
  if (m.q1 == null || m.q3 == null) return { text: `동료 ${m.n}곳 - 비교 안 함`, color: TEXT_FAINT };
  // 2026-11-07 사용자: "가운데 절반보다 위"가 어색함 - 동료 4곳 중 3곳보다 높으면(상위 25%) '동료보다 높음'
  if (m.self > m.q3) return { text: "동료보다 높음", color: TEXT_BODY };
  if (m.self < m.q1) return { text: "동료보다 낮음", color: TEXT_BODY };
  return { text: "동료와 비슷", color: TEXT_SECONDARY };
}
export function ThemePeerSection({ c }: { c: StockRef }) {
  const [themes, setThemes] = useState<PeerTheme[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/radar/peers?market=${c.market}&symbol=${encodeURIComponent(c.symbol)}`)
      .then((r) => r.json())
      .then((d) => { if (!cancelled) setThemes(Array.isArray(d.themes) ? d.themes : []); })
      .catch(() => { if (!cancelled) setThemes([]); });
    return () => { cancelled = true; };
  }, [c.market, c.symbol]);
  if (!themes || themes.length === 0) return null;
  return (
    <div className="p-3 space-y-3" style={{ background: INSET_BG, border: `1px solid ${BORDER}`, borderRadius: 10 }}>
      <p className="text-[12px] font-semibold" style={{ color: TEXT_SECONDARY }}>
        테마 동료 비교 <span className="font-normal" style={{ color: TEXT_MUTED }}>— 같은 테마 사업 소속 기업들 사이에서 이 종목 값 (순위 아님)</span>
      </p>
      {themes.map((t) => (
        <div key={t.theme_id}>
          <p className="text-[12px] mb-1" style={{ color: TEXT_BODY }}>
            <span className="font-bold">{themeName(t.theme_id).ko}</span>
            <span style={{ color: TEXT_MUTED }}> · 소속 {t.members}개사{t.week ? ` · ${t.week.slice(5).replace("-", "/")} 주` : ""}</span>
          </p>
          {/* 넓은 화면은 한 줄(지표·이 종목·중앙값·보통 범위·비교), 휴대폰은 두 줄(아래 줄에 막대·비교) */}
          <div className="text-[12px]" style={{ fontVariantNumeric: "tabular-nums" }}>
            <div className={`hidden sm:grid ${PEER_GRID} py-1`} style={{ color: TEXT_MUTED }}>
              <span>지표</span><span className="text-right">이 종목</span><span className="text-right">테마 중앙값</span>
              <span className="pl-2" title="동료 값을 줄 세웠을 때 가운데 절반(25~75%)">동료 보통 범위</span><span>동료와 비교</span>
            </div>
            {PEER_ROWS.map((row) => {
              const m = t.metrics[row.key];
              if (!m) return null;
              const w = peerWhere(m);
              return (
                <div key={row.key} className={`grid grid-cols-[5.5rem_auto_1fr] ${PEER_GRID} items-center gap-y-1 py-1.5`} style={{ borderTop: `1px solid ${BORDER}` }}>
                  <span style={{ color: TEXT_SECONDARY }} title={row.hint}>{row.label}</span>
                  <span className="text-right font-bold" style={{ color: m.self == null ? TEXT_FAINT : ACCENT }}>{m.self == null ? "-" : row.fmt(m.self)}</span>
                  <span className="text-right" style={{ color: TEXT_BODY }}>
                    <span className="sm:hidden" style={{ color: TEXT_MUTED }}>중앙값 </span>
                    {m.median == null ? <span style={{ color: TEXT_FAINT }}>-</span> : row.fmt(m.median)}
                    <span className="ml-1 text-[11px]" style={{ color: TEXT_FAINT }}>({m.n}곳)</span>
                  </span>
                  <div className="col-span-3 sm:col-span-1 flex items-center gap-2 sm:pl-2">
                    {m.q1 != null && m.q3 != null ? (
                      <div className="flex-1 space-y-0.5">
                        <PeerBar m={m} />
                        <p className="text-[11px]" style={{ color: TEXT_FAINT }}>{row.fmt(m.q1)} ~ {row.fmt(m.q3)}</p>
                      </div>
                    ) : <span className="flex-1" style={{ color: TEXT_FAINT }}>-</span>}
                    <span className="sm:hidden whitespace-nowrap" style={{ color: w.color }}>{w.text}</span>
                  </div>
                  <span className="hidden sm:block whitespace-nowrap" style={{ color: w.color }}>{w.text}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
      <p className="text-[12px]" style={{ color: TEXT_MUTED }}>
        숫자는 저장된 재무 그대로(소속 기업 주간 계산·재무 필터) · 동료 값이 5곳 미만인 지표는 비교하지 않음 · 막대: 노란 띠 = 동료 보통 범위(가운데 절반), 세로선 = 중앙값, 점 = 이 종목 · '동료보다 높음/낮음' = 동료 4곳 중 3곳보다 높거나 낮음 ·
        업종이 섞인 테마는 이익률·FCF 정상 범위가 달라 참고로만
      </p>
    </div>
  );
}

export function MissDetail({ market, symbol }: { market: string; symbol: string }) {
  const [sc, setSc] = useState<{ status: string; piotroski: number | null; reasons: string[]; screened_at: string } | null | undefined>(undefined);
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/watchlist/screening?market=${market}&symbol=${encodeURIComponent(symbol)}`)
      .then((r) => r.json())
      .then((d) => { if (!cancelled) setSc(d.screening ?? null); })
      .catch(() => { if (!cancelled) setSc(null); });
    return () => { cancelled = true; };
  }, [market, symbol]);
  const c: StockRef = { market, symbol };
  const label = sc === undefined ? "확인 중..." : !sc ? "재무 필터 판정 없음(미확인 - 스크리닝 대상 밖이거나 아직 안 돌았음)"
    : sc.status === "pass" ? `재무 필터 통과${sc.piotroski != null ? ` (F-Score ${sc.piotroski})` : ""}`
    : sc.status === "fail" ? "재무 필터 탈락" : "재무 필터 데이터 부족(계산 못 한 항목이 있음 - 탈락 아님)";
  return (
    <div style={{ flexBasis: "100%" }} className="space-y-2">
      <p style={{ color: sc?.status === "fail" ? BAD : sc?.status === "pass" ? GOOD : TEXT_SECONDARY, fontSize: 12 }}>
        {label}
        {sc?.status === "fail" && sc.reasons.length > 0 && <span style={{ color: TEXT_SECONDARY }}> — {sc.reasons.slice(0, 4).join(" · ")}</span>}
        {sc?.screened_at && <span style={{ color: TEXT_SECONDARY }}> · {String(sc.screened_at).slice(0, 10)} 기준</span>}
      </p>
      <ThemePeerSection c={c} />
      <InstitutionSection c={c} />
      <Us8kSection c={c} />
      <InsiderSection c={c} />
    </div>
  );
}

export function ChecklistSection({ c }: { c: StockRef }) {
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
    <div className="p-3 space-y-1.5" style={{ background: INSET_BG, border: `1px solid ${BORDER}`, borderRadius: 10 }}>
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

