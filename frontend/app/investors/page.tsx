"use client";

import { useEffect, useMemo, useState } from "react";
import PageHeader from "@/src/components/PageHeader";
import EmptyState from "@/src/components/EmptyState";
import Note from "@/src/components/Note";
import StockLink from "@/src/components/StockLink";
import { Section, StatGrid, StatTile } from "@/src/components/Section";
import { INVESTOR_BY_ID, STYLE_META, STYLE_NOTE, STYLE_ORDER, investorFull, quarterLabel, usd, type InvestorStyle } from "@/src/lib/institutions";

// 유명 투자자 13F(2026-10-25) - 사용자가 고른 운용사 15곳의 분기 말 보유와 직전 분기 비교(새로·늘림·줄임·다 팖).
// 45일 늦은 매수 보유 사실일 뿐 신호·점수가 아니다(원칙 1). 재무 판정은 재무 필터 3분류 그대로(원칙 4).
type Pos = { ticker: string | null; issuer: string | null; value: number; weight: number | null; status: string | null; share_chg: number | null; prev_value: number | null };
type Manager = { id: string; period: string; filed_on: string; positions: number; value_total: number; compared: boolean;
  counts: { new: number; added: number; reduced: number; sold: number };
  top_holdings: Pos[]; new: Pos[]; added: Pos[]; reduced: Pos[]; sold: Pos[] };
type Shared = { ticker: string; issuer: string | null; buyers: { manager_id: string; status: string; value: number; weight: number | null }[] };
type Screen = Record<string, { status: string; piotroski: number | null; candidate: boolean }>;
type Conviction = Pos & { manager_id: string; period: string };
type Data = { managers: Manager[]; shared: Shared[]; conviction?: Conviction[]; conviction_min?: number; screening: Screen; unmapped: number };

const pct = (v: number | null | undefined, d = 1) => (v == null ? "-" : `${(v * 100).toFixed(d)}%`);
const md = (d: string) => (d ? `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}` : "-");
const ymd = (d: string) => (d ? `${d.slice(0, 4)}.${Number(d.slice(5, 7))}.${Number(d.slice(8, 10))}` : "-");   // 2026.8.14
const daysAgo = (d: string) => (d ? Math.max(0, Math.round((Date.now() - Date.parse(`${d.slice(0, 10)}T00:00:00Z`)) / 86_400_000)) : null);

// 보고서 날짜(2026-11-02, 사용자 요청: 최근 보고서가 언제인지 더 분명하게) - 어느 분기 말 보유인지와 언제 신고했는지를 한 덩어리로.
// 다른 운용사보다 한 분기 이전 보고서면(아직 새 분기 신고 전) 주황 '이전 분기'를 붙인다 - 함께 산 종목에 분기가 섞일 때 알아보게.
function ReportDate({ period, filed, stale }: { period: string; filed: string; stale?: boolean }) {
  const ago = daysAgo(filed);
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 rounded-md px-2 py-0.5 text-[12px] whitespace-nowrap"
      style={{ background: "var(--bg-inset)", border: `1px solid ${stale ? "#fb923c66" : "var(--border-ctrl)"}` }}>
      <span aria-hidden>📄</span>
      <b style={{ color: "var(--text-primary)" }}>{quarterLabel(period)} 보유</b>
      <span style={{ color: "var(--text-muted)" }}>({md(period)} 기준)</span>
      <span style={{ color: "var(--text-faint)" }}>·</span>
      <span style={{ color: "var(--text-secondary)" }}>{ymd(filed)} 신고{ago != null ? ` · ${ago}일 전` : ""}</span>
      {stale && <b style={{ color: "#fb923c" }}>이전 분기</b>}
    </span>
  );
}

function Finance({ s }: { s?: Screen[string] }) {
  const [label, color] = !s ? ["재무 미확인", "var(--text-muted)"]
    : s.status === "pass" ? [`재무 통과${s.piotroski != null ? ` F${s.piotroski}` : ""}`, "#4ade80"]
    : s.status === "fail" ? ["재무 탈락", "#f87171"] : ["데이터 부족", "var(--text-muted)"];
  return (
    <>
      <span className="text-[11px] px-1.5 rounded whitespace-nowrap" style={{ color, border: "1px solid var(--border)" }}>{label}</span>
      {s?.candidate && <span className="text-[11px] px-1.5 rounded whitespace-nowrap" style={{ color: "#ffb020", border: "1px solid #ffb02055" }}>워치리스트 후보</span>}
    </>
  );
}

function Name({ p }: { p: { ticker: string | null; issuer: string | null } }) {
  return p.ticker
    ? <StockLink market="US" symbol={p.ticker} className="font-bold text-white">{p.ticker}</StockLink>
    : <span className="font-bold" style={{ color: "var(--text-secondary)" }} title="CUSIP에서 티커를 못 찾음">{p.issuer ?? "?"}</span>;
}

function PosList({ title, items, kind, screening, empty }: { title: string; items: Pos[]; kind: "new" | "sold" | "added" | "reduced"; screening: Screen; empty: string }) {
  return (
    <div>
      <p className="text-[12px] font-semibold mb-1" style={{ color: kind === "sold" || kind === "reduced" ? "#fca5a5" : kind === "new" ? "#4ade80" : "var(--text-secondary)" }}>{title}</p>
      {items.length === 0 ? <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>{empty}</p> : (
        <div className="space-y-1">
          {items.map((p, i) => (
            <div key={`${p.ticker ?? p.issuer}-${i}`} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] rounded-lg px-2.5 py-1.5"
              style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
              <Name p={p} />
              {p.ticker && <span className="truncate max-w-[12rem]" style={{ color: "var(--text-muted)" }}>{p.issuer}</span>}
              {kind === "sold"
                ? <span style={{ color: "var(--text-secondary)" }}>직전 {usd(p.prev_value)}</span>
                : <span className="text-white">{usd(p.value)}{p.weight != null && <span style={{ color: "var(--text-muted)" }}> · 비중 {pct(p.weight)}</span>}</span>}
              {(kind === "added" || kind === "reduced") && p.share_chg != null &&
                <span style={{ color: kind === "added" ? "#4ade80" : "#f87171" }}>주식 수 {p.share_chg >= 0 ? "+" : ""}{pct(p.share_chg, 0)}</span>}
              {(kind === "new" || kind === "added") && p.ticker && <Finance s={screening[p.ticker]} />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// 보유 비중 막대(2026-10-26 사용자 요청) - 운용사의 주식 보유 구성을 100% 가로 막대 하나로. 원형보다 길이 비교가 정확하다.
// 상위 8종목 + 나머지 '기타'(회색). 색은 한 가지(노랑) - 종목은 색이 아니라 순서·라벨로 구분(막대 안 큰 칸은 티커, 아래 줄에 같은 순서로 티커·비중).
// 칸 사이 2px 틈, 마우스를 올리면 티커·평가액·비중. 비중은 신고서 평가액 그대로(옵션 줄 제외).
function HoldingsBar({ items, total }: { items: Pos[]; total: number }) {
  const shown = items.filter((p) => (p.weight ?? 0) > 0);
  const top = shown.reduce((n, p) => n + (p.weight ?? 0), 0);
  const rest = Math.max(0, 1 - top);
  if (shown.length === 0) return null;
  const label = (p: Pos) => p.ticker ?? (p.issuer ?? "?").split(" ")[0];
  return (
    <div className="mb-2.5" role="img" aria-label={`보유 비중: ${shown.map((p) => `${label(p)} ${pct(p.weight, 0)}`).join(", ")}${rest > 0.005 ? `, 기타 ${pct(rest, 0)}` : ""}`}>
      <div className="flex h-5 w-full gap-[2px] overflow-hidden rounded">
        {shown.map((p, i) => (
          <div key={i} className="flex items-center justify-center overflow-hidden text-[11px] font-bold first:rounded-l last:rounded-r"
            style={{ width: `${(p.weight ?? 0) * 100}%`, background: i % 2 ? "#e09a16" : "#ffb020", color: "#1a1408", minWidth: 2 }}
            title={`${label(p)}${p.issuer && p.ticker ? ` (${p.issuer})` : ""} · ${usd(p.value)} · 비중 ${pct(p.weight)}`}>
            {/* 막대 안 티커: 12% 이상은 항상, 8~12%는 넓은 화면만(휴대폰에선 'G…'처럼 잘린다) - 아래 줄에 전부 있다 */}
            {(p.weight ?? 0) >= 0.08 && <span className={`truncate px-1 ${(p.weight ?? 0) < 0.12 ? "hidden sm:inline" : ""}`}>{label(p)}</span>}
          </div>
        ))}
        {rest > 0.005 && (
          <div className="flex items-center justify-center rounded-r text-[11px]" title={`나머지 ${Math.max(0, total - shown.length)}종목 · 비중 ${pct(rest)}`}
            style={{ width: `${rest * 100}%`, background: "#3a3424", color: "var(--text-secondary)" }}>
            {rest >= 0.1 && <span className="truncate px-1">기타</span>}
          </div>
        )}
      </div>
      <p className="mt-1 flex flex-wrap gap-x-2.5 gap-y-0.5 text-[12px]" style={{ color: "var(--text-muted)" }}>
        {shown.map((p, i) => (
          <span key={i} className="whitespace-nowrap"><Name p={p} /> {pct(p.weight, 0)}</span>
        ))}
        {rest > 0.005 && <span className="whitespace-nowrap">기타 {Math.max(0, total - shown.length)}종목 {pct(rest, 0)}</span>}
      </p>
    </div>
  );
}

// 투자 스타일 배지(2026-11-02, 사용자 요청: 분류가 눈에 잘 안 띈다) - 색은 구분용, 좋고 나쁨이 아니다
function StyleChip({ s, size = "sm" }: { s?: InvestorStyle; size?: "sm" | "md" }) {
  if (!s) return null;
  const { emoji, color } = STYLE_META[s];
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full font-semibold ${size === "md" ? "px-2.5 py-0.5 text-[12.5px]" : "px-2 text-[11px]"}`}
      style={{ background: color + "1a", border: `1px solid ${color}55`, color }}>
      <span aria-hidden>{emoji}</span>{s}
    </span>
  );
}

// 스타일 묶음 머리 - 예전엔 회색 작은 글씨 한 줄(GroupTitle)이라 묶음이 바뀌는 게 안 보였다
function StyleGroup({ s, count, children }: { s: InvestorStyle; count: number; children: React.ReactNode }) {
  if (count === 0) return null;
  const { emoji, color } = STYLE_META[s];
  return (
    <div id={`style-${STYLE_ORDER.indexOf(s)}`} className="space-y-2 scroll-mt-4">
      <div className="mt-4 rounded-lg px-3 py-2.5" style={{ background: color + "10", borderLeft: `4px solid ${color}` }}>
        <p className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-[16px] font-extrabold" style={{ color }}>{emoji} {s}</span>
          <span className="text-[13px] font-bold" style={{ color: "var(--text-secondary)" }}>{count}곳</span>
        </p>
        <p className="mt-0.5 text-[12.5px]" style={{ color: "var(--text-secondary)" }}>{STYLE_NOTE[s]}</p>
      </div>
      {children}
    </div>
  );
}

function ManagerCard({ m, screening, latestPeriod }: { m: Manager; screening: Screen; latestPeriod: string }) {
  const meta = INVESTOR_BY_ID[m.id];
  const [more, setMore] = useState(false);
  return (
    <Section title={<span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">{meta?.ko ?? m.id}
        {meta?.person && <span className="text-[13px] font-semibold" style={{ color: "var(--text-secondary)" }}>{meta.person}</span>}
        <StyleChip s={meta?.style} /></span>}
      sub={<>{meta?.en} · 보유 {m.positions}종목 · {usd(m.value_total)}</>}
      right={m.compared && <span style={{ color: "var(--text-muted)" }}>신규 {m.counts.new} · 추가 {m.counts.added} · 일부 매도 {m.counts.reduced} · 전량 매도 {m.counts.sold}</span>}>
      <div className="mb-2"><ReportDate period={m.period} filed={m.filed_on} stale={!!latestPeriod && m.period < latestPeriod} /></div>
      <HoldingsBar items={m.top_holdings} total={m.positions} />
      {!m.compared ? (
        <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>직전 분기 신고가 없어 비교하지 않습니다.</p>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <PosList title={`신규 매수 ${m.counts.new}`} items={m.new} kind="new" screening={screening} empty="없음" />
            <PosList title={`전량 매도 ${m.counts.sold}`} items={m.sold} kind="sold" screening={screening} empty="없음" />
          </div>
          {(m.counts.added + m.counts.reduced) > 0 && (
            <>
              <button onClick={() => setMore(!more)} className="mt-2 text-[12px] hover:underline" style={{ color: "#ffb020" }}>
                {more ? "접기" : `추가 매수·일부 매도 보기 (추가 ${m.counts.added} · 일부 매도 ${m.counts.reduced})`}
              </button>
              {more && (
                <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-3">
                  <PosList title="늘린 종목 (늘어난 평가액 순)" items={m.added} kind="added" screening={screening} empty="없음" />
                  <PosList title="줄인 종목 (줄어든 평가액 순)" items={m.reduced} kind="reduced" screening={screening} empty="없음" />
                </div>
              )}
            </>
          )}
        </>
      )}
    </Section>
  );
}

export default function InvestorsPage() {
  const [d, setD] = useState<Data | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    fetch("/api/investors").then((r) => r.json())
      .then((x) => (x && Array.isArray(x.managers) ? setD(x) : setErr(true))).catch(() => setErr(true));
  }, []);

  const latestFiled = useMemo(() => (d?.managers ?? []).reduce((m, x) => (x.filed_on > m ? x.filed_on : m), ""), [d]);
  const latestPeriod = useMemo(() => (d?.managers ?? []).reduce((m, x) => (x.period > m ? x.period : m), ""), [d]);
  const staleCount = (d?.managers ?? []).filter((m) => latestPeriod && m.period < latestPeriod).length;
  const newTotal = (d?.managers ?? []).reduce((n, m) => n + m.counts.new, 0);
  const byStyle = (s: InvestorStyle) => (d?.managers ?? []).filter((m) => INVESTOR_BY_ID[m.id]?.style === s)
    .sort((a, b) => Object.keys(INVESTOR_BY_ID).indexOf(a.id) - Object.keys(INVESTOR_BY_ID).indexOf(b.id));

  return (
    <div className="space-y-3">
      <PageHeader title="유명 투자자 13F" intro="investors"
        asOf={latestFiled && <span className="text-[12.5px] font-semibold" style={{ color: "var(--text-secondary)" }}>📄 최근 신고 {ymd(latestFiled)}{daysAgo(latestFiled) != null ? ` (${daysAgo(latestFiled)}일 전)` : ""} · 분기마다 갱신</span>}
        desc="직접 고른 운용사 15곳이 분기 말 무엇을 새로 사고 다 팔았는지(SEC 13F). 45일 늦은 매수 보유 사실 - 매수 신호가 아닙니다." />

      {err ? <EmptyState title="불러오지 못했습니다" /> : !d ? (
        <div className="h-24 rounded-xl animate-pulse" style={{ background: "#111009" }} />
      ) : d.managers.length === 0 ? (
        <EmptyState title="아직 받은 13F가 없습니다" hint="매일 확인해 새 신고가 있으면 받습니다(GitHub → Actions → Collect 13F). 13F는 분기 끝나고 45일 안에 나옵니다." />
      ) : (
        <>
          <StatGrid cols={4}>
            <StatTile label="추적 운용사" value={d.managers.length} sub="투자 스타일 5가지로 묶음" href="#styles" />
            <StatTile label="최근 보고서" value={quarterLabel(latestPeriod)}
              sub={`${md(latestPeriod)} 보유 기준 · ${ymd(latestFiled)} 신고${staleCount ? ` · 이전 분기 ${staleCount}곳` : ""}`}
              hint="13F는 분기 말 보유를 45일 안에 신고합니다. 운용사마다 신고일이 달라, 새 분기 신고 전인 곳은 '이전 분기'로 표시합니다." />
            <StatTile label="2곳 이상이 함께 산 종목" value={d.shared.length} emphasis={d.shared.length ? "accent" : undefined} sub="신규·추가 매수" href="#shared" />
            <StatTile label="확신 매수" value={(d.conviction ?? []).length} href="#conviction"
              sub={`신규 매수 중 비중 ${Math.round((d.conviction_min ?? 0.03) * 100)}% 이상`} hint={`신규 매수 전체(운용사별 합) ${newTotal}`} />
          </StatGrid>

          <Section id="shared" title="여러 곳이 함께 산 종목" count={d.shared.length}
            info="각 운용사의 가장 최근 분기에 신규·추가 매수한 종목 중 2곳 이상이 함께 산 것. 함께 산 곳이 많은 순이며 점수가 아닙니다."
            sub="각자 가장 최근 분기 기준">
            {d.shared.length === 0 ? <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>함께 산 종목 없음</p> : (
              <div className="space-y-1">
                {d.shared.slice(0, 20).map((t) => (
                  <div key={t.ticker} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] rounded-lg px-3 py-1.5"
                    style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                    <Name p={t} />
                    <span className="truncate max-w-[14rem]" style={{ color: "var(--text-muted)" }}>{t.issuer}</span>
                    {t.buyers.map((b) => (
                      <span key={b.manager_id} className="px-1.5 rounded whitespace-nowrap"
                        style={{ background: b.status === "new" ? "#4ade8014" : "transparent", border: `1px solid ${b.status === "new" ? "#4ade8044" : "var(--border)"}`,
                          color: b.status === "new" ? "#4ade80" : "var(--text-secondary)" }}>
                        {INVESTOR_BY_ID[b.manager_id]?.ko ?? b.manager_id} {b.status === "new" ? "신규" : "추가"}
                      </span>
                    ))}
                    <Finance s={d.screening[t.ticker]} />
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* 확신 매수(2026-10-26) - 새로 산 종목 중 그 운용사 주식 보유의 일정 비중 이상. 개수보다 '얼마나 크게 실었나' */}
          <Section id="conviction" title="확신 매수" count={(d.conviction ?? []).length}
            info={`신규 매수 종목 중 그 운용사 주식 보유에서 비중이 ${Math.round((d.conviction_min ?? 0.03) * 100)}% 이상인 것. 새 종목에 크게 실었다는 뜻이라 개수보다 무게가 있습니다. 기준은 임의값이고, 소수 종목에 집중하는 운용사가 자주 걸립니다. 비중 큰 순 - 점수가 아닙니다.`}
            sub={`신규 매수 중 비중 ${Math.round((d.conviction_min ?? 0.03) * 100)}% 이상 · 비중 큰 순`}>
            {(d.conviction ?? []).length === 0 ? <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>해당 없음</p> : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                {(d.conviction ?? []).map((x, i) => (
                  <div key={`${x.manager_id}-${x.ticker ?? x.issuer}-${i}`} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] rounded-lg px-3 py-1.5"
                    style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                    <Name p={x} />
                    {x.ticker && <span className="truncate max-w-[10rem]" style={{ color: "var(--text-muted)" }}>{x.issuer}</span>}
                    <span className="font-bold" style={{ color: "#ffb020" }}>비중 {pct(x.weight)}</span>
                    <span className="text-white">{usd(x.value)}</span>
                    <span style={{ color: "var(--text-secondary)" }}>{investorFull(INVESTOR_BY_ID[x.manager_id]) || x.manager_id}
                      <span style={{ color: "var(--text-faint)" }}> · {quarterLabel(x.period)}</span></span>
                    <StyleChip s={INVESTOR_BY_ID[x.manager_id]?.style} />
                    {x.ticker && <Finance s={d.screening[x.ticker]} />}
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* 스타일 바로 가기 - 누르면 그 묶음으로 */}
          <div id="styles" className="flex flex-wrap items-center gap-1.5 pt-2 scroll-mt-4">
            <span className="text-[12px] mr-1" style={{ color: "var(--text-muted)" }}>투자 스타일</span>
            {STYLE_ORDER.filter((s) => byStyle(s).length > 0).map((s) => (
              <a key={s} href={`#style-${STYLE_ORDER.indexOf(s)}`} className="hover:brightness-125" title={STYLE_NOTE[s]}>
                <StyleChip s={s} size="md" /> <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>{byStyle(s).length}</span>
              </a>
            ))}
          </div>
          {STYLE_ORDER.map((s) => (
            <StyleGroup key={s} s={s} count={byStyle(s).length}>
              {byStyle(s).map((m) => <ManagerCard key={m.id} m={m} screening={d.screening} latestPeriod={latestPeriod} />)}
            </StyleGroup>
          ))}

          <Note label="읽는 법·한계">
            13F는 미국 상장주식을 1억 달러 넘게 굴리는 운용사가 분기 말 보유를 45일 안에 신고한 것입니다. 산 시점·가격은 알 수 없고 이미 팔았을 수도 있습니다.
            매수 보유만 나옵니다(공매도·현금·해외 주식 없음, 옵션 줄은 이 화면에서 뺌). 버크셔처럼 비공개 승인을 받아 나중에 정정 신고로 더하는 종목이 있습니다(받으면 그 분기에 더함).
            주식 수 변화에는 액면분할이 섞일 수 있습니다. 평가액은 분기 말 가격 기준. 티커는 CUSIP을 OpenFIGI로 바꾼 것이라, 못 찾은 종목은 회사명으로 보입니다
            {d.unmapped > 0 && ` (지금 ${d.unmapped}개)`}. 재무 판정은 재무 필터 기준(미국 유니버스 밖 종목은 미확인).
          </Note>
        </>
      )}
    </div>
  );
}
