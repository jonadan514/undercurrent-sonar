"use client";

import { useEffect, useMemo, useState } from "react";
import PageHeader from "@/src/components/PageHeader";
import EmptyState from "@/src/components/EmptyState";
import Note from "@/src/components/Note";
import StockLink from "@/src/components/StockLink";
import { GroupTitle, Section, StatGrid, StatTile } from "@/src/components/Section";
import { INVESTOR_BY_ID, STYLE_NOTE, STYLE_ORDER, quarterLabel, usd, type InvestorStyle } from "@/src/lib/institutions";

// 유명 투자자 13F(2026-10-25) - 사용자가 고른 운용사 15곳의 분기 말 보유와 직전 분기 비교(새로·늘림·줄임·다 팖).
// 45일 늦은 매수 보유 사실일 뿐 신호·점수가 아니다(원칙 1). 재무 판정은 트랩 필터 3분류 그대로(원칙 4).
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

function Finance({ s }: { s?: Screen[string] }) {
  const [label, color] = !s ? ["재무 미확인", "var(--text-muted)"]
    : s.status === "pass" ? [`재무 통과${s.piotroski != null ? ` F${s.piotroski}` : ""}`, "#4ade80"]
    : s.status === "fail" ? ["재무 탈락", "#f87171"] : ["데이터부족", "var(--text-muted)"];
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

function ManagerCard({ m, screening }: { m: Manager; screening: Screen }) {
  const meta = INVESTOR_BY_ID[m.id];
  const [more, setMore] = useState(false);
  return (
    <Section title={meta?.ko ?? m.id}
      sub={<>{meta?.en} · <b style={{ color: "var(--text-secondary)" }}>{quarterLabel(m.period)}</b> 말 기준 · {md(m.filed_on)} 신고 · 보유 {m.positions}종목 · {usd(m.value_total)}</>}
      right={m.compared && <span style={{ color: "var(--text-muted)" }}>새로 {m.counts.new} · 늘림 {m.counts.added} · 줄임 {m.counts.reduced} · 다 팖 {m.counts.sold}</span>}>
      <p className="text-[12px] mb-2" style={{ color: "var(--text-muted)" }}>
        주요 보유: {m.top_holdings.map((p, i) => <span key={i}>{i > 0 && " · "}<Name p={p} /> {pct(p.weight, 0)}</span>)}
      </p>
      {!m.compared ? (
        <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>직전 분기 신고가 없어 비교하지 않습니다.</p>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <PosList title={`새로 산 종목 ${m.counts.new}`} items={m.new} kind="new" screening={screening} empty="없음" />
            <PosList title={`다 판 종목 ${m.counts.sold}`} items={m.sold} kind="sold" screening={screening} empty="없음" />
          </div>
          {(m.counts.added + m.counts.reduced) > 0 && (
            <>
              <button onClick={() => setMore(!more)} className="mt-2 text-[12px] hover:underline" style={{ color: "#ffb020" }}>
                {more ? "접기" : `늘리고 줄인 종목 보기 (늘림 ${m.counts.added} · 줄임 ${m.counts.reduced})`}
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
  const newTotal = (d?.managers ?? []).reduce((n, m) => n + m.counts.new, 0);
  const byStyle = (s: InvestorStyle) => (d?.managers ?? []).filter((m) => INVESTOR_BY_ID[m.id]?.style === s)
    .sort((a, b) => Object.keys(INVESTOR_BY_ID).indexOf(a.id) - Object.keys(INVESTOR_BY_ID).indexOf(b.id));

  return (
    <div className="space-y-3">
      <PageHeader title="유명 투자자 13F" intro="investors"
        asOf={latestFiled && <span className="text-[12px]" style={{ color: "var(--text-faint)" }}>최근 신고 {latestFiled} · 분기마다 갱신</span>}
        desc="직접 고른 운용사 15곳이 분기 말 무엇을 새로 사고 다 팔았는지(SEC 13F). 45일 늦은 매수 보유 사실 - 매수 신호가 아닙니다." />

      {err ? <EmptyState title="불러오지 못했습니다" /> : !d ? (
        <div className="h-24 rounded-xl animate-pulse" style={{ background: "#111009" }} />
      ) : d.managers.length === 0 ? (
        <EmptyState title="아직 받은 13F가 없어요" hint="매일 확인해 새 신고가 있으면 받습니다(GitHub → Actions → Collect 13F). 13F는 분기 끝나고 45일 안에 나옵니다." />
      ) : (
        <>
          <StatGrid cols={4}>
            <StatTile label="추적 운용사" value={d.managers.length} sub="스타일별 아래 묶음" />
            <StatTile label="최근 분기" value={quarterLabel(latestPeriod)} sub={`분기 말 기준 · ${md(latestFiled)} 신고까지`} />
            <StatTile label="2곳 이상이 함께 산 종목" value={d.shared.length} emphasis={d.shared.length ? "accent" : undefined} sub="새로 사거나 늘림" href="#shared" />
            <StatTile label="확신 매수" value={(d.conviction ?? []).length} href="#conviction"
              sub={`새로 샀는데 비중 ${Math.round((d.conviction_min ?? 0.03) * 100)}% 이상`} hint={`새로 산 종목 전체(운용사별 합) ${newTotal}`} />
          </StatGrid>

          <Section id="shared" title="여러 곳이 함께 산 종목" count={d.shared.length}
            info="각 운용사의 가장 최근 분기에 새로 사거나 주식 수를 늘린 종목 중 2곳 이상 겹친 것. 많이 겹친 순 - 점수가 아닙니다."
            sub="각자 가장 최근 분기 기준">
            {d.shared.length === 0 ? <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>겹친 종목 없음</p> : (
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
                        {INVESTOR_BY_ID[b.manager_id]?.ko.split(" (")[0] ?? b.manager_id} {b.status === "new" ? "새로" : "늘림"}
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
            info={`새로 산 종목 중 그 운용사 주식 보유에서 비중이 ${Math.round((d.conviction_min ?? 0.03) * 100)}% 이상인 것. 새 종목에 크게 실었다는 뜻이라 개수보다 무게가 있습니다. 기준은 임의값이고, 소수 종목에 집중하는 운용사가 자주 걸립니다. 비중 큰 순 - 점수가 아닙니다.`}
            sub={`새로 샀는데 비중 ${Math.round((d.conviction_min ?? 0.03) * 100)}% 이상 · 비중 큰 순`}>
            {(d.conviction ?? []).length === 0 ? <p className="text-[12px]" style={{ color: "var(--text-faint)" }}>해당 없음</p> : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                {(d.conviction ?? []).map((x, i) => (
                  <div key={`${x.manager_id}-${x.ticker ?? x.issuer}-${i}`} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] rounded-lg px-3 py-1.5"
                    style={{ background: "var(--bg-inset)", border: "1px solid var(--border)" }}>
                    <Name p={x} />
                    {x.ticker && <span className="truncate max-w-[10rem]" style={{ color: "var(--text-muted)" }}>{x.issuer}</span>}
                    <span className="font-bold" style={{ color: "#ffb020" }}>비중 {pct(x.weight)}</span>
                    <span className="text-white">{usd(x.value)}</span>
                    <span style={{ color: "var(--text-secondary)" }}>{INVESTOR_BY_ID[x.manager_id]?.ko.split(" (")[0] ?? x.manager_id}
                      <span style={{ color: "var(--text-faint)" }}> · {INVESTOR_BY_ID[x.manager_id]?.style} · {quarterLabel(x.period)}</span></span>
                    {x.ticker && <Finance s={d.screening[x.ticker]} />}
                  </div>
                ))}
              </div>
            )}
          </Section>

          {STYLE_ORDER.map((s) => (
            <GroupTitle key={s} title={`${s} — ${STYLE_NOTE[s]}`}>
              {byStyle(s).map((m) => <ManagerCard key={m.id} m={m} screening={d.screening} />)}
            </GroupTitle>
          ))}

          <Note label="읽는 법·한계">
            13F는 미국 상장주식을 1억 달러 넘게 굴리는 운용사가 분기 말 보유를 45일 안에 신고한 것입니다. 산 시점·가격은 알 수 없고 이미 팔았을 수도 있습니다.
            매수 보유만 나옵니다(공매도·현금·해외 주식 없음, 옵션 줄은 이 화면에서 뺌). 버크셔처럼 비공개 승인을 받아 나중에 정정 신고로 더하는 종목이 있습니다(받으면 그 분기에 더함).
            주식 수 변화에는 액면분할이 섞일 수 있습니다. 평가액은 분기 말 가격 기준. 티커는 CUSIP을 OpenFIGI로 바꾼 것이라, 못 찾은 종목은 회사명으로 보입니다
            {d.unmapped > 0 && ` (지금 ${d.unmapped}줄)`}. 재무는 트랩 필터 판정(미국 유니버스 밖 종목은 미확인).
          </Note>
        </>
      )}
    </div>
  );
}
