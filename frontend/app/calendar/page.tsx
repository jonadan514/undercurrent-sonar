"use client";

import { Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import FlagIcon from "@/src/components/FlagIcon";
import PageHeader from "@/src/components/PageHeader";
import { Section } from "@/src/components/Section";

// 일정(2026-11-07, 마스터 플랜 2단계 '일정 기능'). 실적 발표 · 공시 마감 · 관찰 노트 회고 · 브리핑/월간 보고서 날을 한 달 달력에.
// 데이터는 /api/calendar(새 수집 없음). 점수·순위 없음 - 내 관심 → 노트 → 후보 → 테마 순으로 보여 줄 뿐(원칙 1).

type Mk = "US" | "KR";
type Tag = "my" | "note" | "candidate" | "theme";
interface CalEvent {
  date: string; kind: "earnings" | "review" | "deadline" | "tool"; market?: Mk; symbol?: string; name?: string;
  estimate?: boolean; source?: string; tags?: Tag[]; themes?: string[]; text?: string; href?: string;
}
interface Data { month: string; from: string; to: string; today: string; events: CalEvent[]; notes: string[] }

const TAG_KO: Record<Tag, string> = { my: "내 관심", note: "노트", candidate: "후보", theme: "테마" };
const ACCENT = "var(--accent)";
const MUTED = { color: "var(--text-muted)" };
const FAINT = { color: "var(--text-faint)" };
const WD = ["월", "화", "수", "목", "금", "토", "일"];

const monthKo = (m: string) => `${m.slice(0, 4)}년 ${Number(m.slice(5))}월`;
const shiftMonth = (m: string, n: number) => {
  const [y, mm] = m.split("-").map(Number);
  const d = new Date(Date.UTC(y, mm - 1 + n, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
};
const dayKo = (d: string) => {
  const wd = WD[(new Date(`${d}T00:00:00Z`).getUTCDay() + 6) % 7];
  return `${Number(d.slice(5, 7))}/${Number(d.slice(8))}(${wd})`;
};

// 실적 종목 색: 내 관심 = 앰버, 노트 = 청록, 그 밖 = 본문색
const tone = (e: CalEvent) => e.tags?.includes("my") ? ACCENT : e.tags?.includes("note") ? "var(--info)" : "var(--text-secondary)";

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button onClick={onClick} className="rounded-full px-2.5 py-1 text-[12.5px]"
      style={{ border: `1px solid ${on ? ACCENT : "var(--border-ctrl)"}`, color: on ? ACCENT : "var(--text-muted)", background: on ? "#ffb02012" : "transparent" }}>
      {children}
    </button>
  );
}

function EventLine({ e, compact }: { e: CalEvent; compact?: boolean }) {
  if (e.kind === "deadline") {
    return <div className="text-[12px] font-bold leading-snug" style={{ color: "var(--orange)" }}>📌 {e.text}</div>;
  }
  if (e.kind === "tool") {
    return <a href={e.href} className="block text-[11.5px] leading-snug hover:underline" style={FAINT}>· {e.text}</a>;
  }
  if (e.kind === "review") {
    return (
      <a href={e.href} className="block text-[12px] leading-snug hover:underline" style={{ color: "var(--info)" }}>
        🔁 {e.name} <span style={FAINT}>{compact ? "회고" : e.text}</span>
      </a>
    );
  }
  return (
    <a href={e.href} className="flex items-baseline gap-1 text-[12px] leading-snug hover:underline" style={{ color: tone(e) }}
      title={`${e.name} · ${e.market === "KR" ? "한국" : "미국"} · ${(e.tags ?? []).map((t) => TAG_KO[t]).join("·")}${e.estimate ? " · 날짜 미확정" : ""}`}>
      <span className="shrink-0"><FlagIcon market={e.market!} size={11} /></span>
      <span className={`truncate ${e.tags?.includes("my") ? "font-bold" : ""}`}>{e.name}</span>
      {e.estimate && <span className="shrink-0 text-[10px]" style={FAINT}>?</span>}
      {!compact && (
        <span className="ml-1 shrink-0 text-[11px]" style={FAINT}>
          {(e.tags ?? []).map((t) => TAG_KO[t]).join(" · ")}
          {e.themes?.length ? ` · ${e.themes.join(", ")}` : ""}
          {e.estimate ? " · 날짜 미확정" : e.source === "DART" ? " · 공시 예고" : ""}
        </span>
      )}
    </a>
  );
}

function CalendarView() {
  const params = useSearchParams();
  const router = useRouter();
  const [data, setData] = useState<Data | null>(null);
  const [mine, setMine] = useState(true);       // 내 관심·노트
  const [cand, setCand] = useState(true);       // 후보
  const [theme, setTheme] = useState(false);    // 테마 소속(후보 아닌 것) - 많아서 기본은 끔
  const [mk, setMk] = useState<"ALL" | Mk>("ALL");
  const [tools, setTools] = useState(true);
  const [picked, setPicked] = useState<string | null>(null);
  const month = params.get("month") ?? "";

  useEffect(() => {
    setData(null);
    fetch(`/api/calendar${month ? `?month=${month}` : ""}`).then((r) => r.json()).then(setData).catch(() => setData(null));
  }, [month]);

  const shown = useMemo(() => (data?.events ?? []).filter((e) => {
    if (e.kind === "tool") return tools;
    if (e.kind === "deadline") return true;
    if (mk !== "ALL" && e.market && e.market !== mk) return false;
    if (e.kind === "review") return mine;
    const t = e.tags ?? [];
    return (mine && (t.includes("my") || t.includes("note"))) || (cand && t.includes("candidate")) || (theme && t.includes("theme"));
  }), [data, mine, cand, theme, mk, tools]);

  const byDay = useMemo(() => {
    const m = new Map<string, CalEvent[]>();
    for (const e of shown) m.set(e.date, [...(m.get(e.date) ?? []), e]);
    return m;
  }, [shown]);

  // 휴대폰: 처음 열면 오늘(또는 다음 일정 날)로 내려간다 - 지난 날부터 길게 넘기지 않게
  useEffect(() => {
    if (!data || typeof window === "undefined" || window.innerWidth >= 768) return;
    const target = data.events.map((e) => e.date).filter((d) => d >= data.today && d <= data.to).sort()[0];
    if (target && target > data.from) document.getElementById(`day-${target}`)?.scrollIntoView({ block: "start" });
  }, [data]);

  if (!data) return <p className="text-[13px]" style={MUTED}>불러오는 중…</p>;
  const cur = data.month;
  const go = (m: string) => router.push(`/calendar?month=${m}`);
  const earnAll = data.events.filter((e) => e.kind === "earnings");
  const cnt = (t: Tag) => earnAll.filter((e) => e.tags?.includes(t)).length;

  // 달력 칸: 그 달 1일이 든 주의 월요일부터 말일이 든 주의 일요일까지
  const first = new Date(`${data.from}T00:00:00Z`);
  const start = new Date(first); start.setUTCDate(first.getUTCDate() - ((first.getUTCDay() + 6) % 7));
  const days: string[] = [];
  for (let d = new Date(start); ; d.setUTCDate(d.getUTCDate() + 1)) {
    const s = d.toISOString().slice(0, 10);
    if (s > data.to && days.length % 7 === 0) break;
    days.push(s);
  }
  const agenda = [...byDay.entries()].filter(([d]) => d >= data.from && d <= data.to);
  // 오늘(이 달이면) 이후 처음 일정이 있는 날 - 데스크톱 기본 선택, 휴대폰은 거기로 내려간다
  const nextDay = agenda.find(([d]) => d >= data.today)?.[0] ?? null;
  const sel = picked ?? nextDay ?? agenda[0]?.[0] ?? null;

  return (
    <div className="space-y-4">
      <PageHeader title="일정" desc="실적 발표 · 공시 마감 · 관찰 노트 회고 · 브리핑 나오는 날을 한 달에. 실적 발표일은 매주 일요일 받는 예정일이라 바뀔 수 있습니다(물음표는 회사가 아직 확정하지 않은 날짜).">
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button onClick={() => go(shiftMonth(cur, -1))} className="rounded px-2 py-1 text-[13px]" style={{ border: "1px solid var(--border-ctrl)", color: "var(--text-secondary)" }}>←</button>
          <span className="min-w-[7.5rem] text-center text-[15px] font-bold" style={{ color: "var(--text-primary)" }}>{monthKo(cur)}</span>
          <button onClick={() => go(shiftMonth(cur, 1))} className="rounded px-2 py-1 text-[13px]" style={{ border: "1px solid var(--border-ctrl)", color: "var(--text-secondary)" }}>→</button>
          {cur !== data.today.slice(0, 7) && <button onClick={() => go(data.today.slice(0, 7))} className="text-[12.5px] hover:underline" style={{ color: ACCENT }}>이번 달</button>}
        </div>
      </PageHeader>

      <div className="flex flex-wrap items-center gap-1.5">
        <Chip on={mine} onClick={() => setMine(!mine)}>내 관심·노트 {cnt("my") + cnt("note") > 0 ? cnt("my") + cnt("note") : ""}</Chip>
        <Chip on={cand} onClick={() => setCand(!cand)}>후보 {cnt("candidate") || ""}</Chip>
        <Chip on={theme} onClick={() => setTheme(!theme)}>테마 소속 {cnt("theme") || ""}</Chip>
        <span className="mx-1 h-4 w-px" style={{ background: "var(--border)" }} />
        <Chip on={mk === "ALL"} onClick={() => setMk("ALL")}>전체</Chip>
        <Chip on={mk === "US"} onClick={() => setMk("US")}>미국</Chip>
        <Chip on={mk === "KR"} onClick={() => setMk("KR")}>한국</Chip>
        <span className="mx-1 h-4 w-px" style={{ background: "var(--border)" }} />
        <Chip on={tools} onClick={() => setTools(!tools)}>브리핑·보고서 날</Chip>
      </div>
      {data.notes.length > 0 && <p className="text-[12px]" style={{ color: "var(--orange)" }}>{data.notes.join(" ")}</p>}

      {/* 데스크톱: 달력 칸 */}
      <div className="hidden md:block">
        <div className="grid grid-cols-7 overflow-hidden rounded-xl" style={{ border: "1px solid var(--border)" }}>
          {WD.map((w, i) => (
            <div key={w} className="px-2 py-1.5 text-[12px] font-bold" style={{ background: "var(--bg-inset)", color: i >= 5 ? "var(--text-faint)" : "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>{w}</div>
          ))}
          {days.map((d, i) => {
            const inMonth = d >= data.from && d <= data.to;
            const evs = byDay.get(d) ?? [];
            const fixed = evs.filter((e) => e.kind !== "earnings");
            const earn = evs.filter((e) => e.kind === "earnings");
            const MAX = 5;
            return (
              <div key={d} onClick={() => setPicked(d)} role="button" tabIndex={0}
                onKeyDown={(ev) => { if (ev.key === "Enter") setPicked(d); }}
                className="min-h-[7.5rem] cursor-pointer p-1.5 text-left align-top"
                style={{ borderRight: i % 7 !== 6 ? "1px solid var(--border-dim)" : undefined, borderTop: i >= 7 ? "1px solid var(--border-dim)" : undefined,
                         background: d === sel ? "#ffb0200d" : inMonth ? "var(--bg-card)" : "var(--bg-base)", opacity: inMonth ? 1 : 0.45 }}>
                <div className="mb-0.5 flex items-center gap-1">
                  <span className="text-[12px] font-bold" style={{ color: d === data.today ? "#0a0a08" : "var(--text-secondary)", background: d === data.today ? ACCENT : "transparent",
                    borderRadius: 999, padding: d === data.today ? "0 6px" : 0 }}>{Number(d.slice(8))}</span>
                  {earn.length > 0 && <span className="text-[10.5px]" style={FAINT}>실적 {earn.length}</span>}
                </div>
                <div className="space-y-0.5">
                  {fixed.map((e, j) => <EventLine key={`f${j}`} e={e} compact />)}
                  {earn.slice(0, MAX).map((e) => <EventLine key={`${e.market}:${e.symbol}`} e={e} compact />)}
                  {earn.length > MAX && <div className="text-[11px]" style={FAINT}>외 {earn.length - MAX}곳</div>}
                </div>
              </div>
            );
          })}
        </div>
        <p className="mt-1.5 text-[12px]" style={FAINT}>
          이름 색: <span style={{ color: ACCENT }}>내 관심</span> · <span style={{ color: "var(--info)" }}>관찰 노트</span> · 그 밖(후보·테마). 칸을 누르면 아래에 그날 전체가 나옵니다.
        </p>
      </div>

      {/* 데스크톱: 고른 날 자세히 */}
      {sel && (
        <div className="hidden md:block">
          <Section title={dayKo(sel)} count={(byDay.get(sel) ?? []).filter((e) => e.kind === "earnings").length ? `실적 ${(byDay.get(sel) ?? []).filter((e) => e.kind === "earnings").length}곳` : undefined}>
            {(byDay.get(sel) ?? []).length ? (
              <div className="grid gap-x-6 gap-y-1 lg:grid-cols-2">
                {(byDay.get(sel) ?? []).map((e, j) => <EventLine key={j} e={e} />)}
              </div>
            ) : <p className="text-[13px]" style={MUTED}>이날 일정이 없습니다.</p>}
          </Section>
        </div>
      )}

      {/* 휴대폰: 날짜별 목록 */}
      <div className="space-y-2 md:hidden">
        {agenda.length === 0 && <p className="text-[13px]" style={MUTED}>이 달에 고른 조건의 일정이 없습니다.</p>}
        {agenda.map(([d, evs]) => (
          <div key={d} id={`day-${d}`} className="scroll-mt-20 rounded-lg p-2.5" style={{ border: `1px solid ${d === data.today ? ACCENT : "var(--border)"}`, background: "var(--bg-card)", opacity: d < data.today ? 0.6 : 1 }}>
            <div className="mb-1 flex items-baseline gap-2">
              <span className="text-[13.5px] font-bold" style={{ color: d === data.today ? ACCENT : "var(--text-primary)" }}>{dayKo(d)}</span>
              {d === data.today && <span className="text-[11px]" style={{ color: ACCENT }}>오늘</span>}
            </div>
            <div className="space-y-1">{evs.map((e, j) => <EventLine key={j} e={e} />)}</div>
          </div>
        ))}
      </div>

      <p className="text-[12px]" style={FAINT}>
        실적 발표일은 워치리스트 후보·내 관심·관찰 노트 종목만 받습니다(테마 소속이라도 후보가 아니면 없을 수 있음). 한국은 회사가 공시로 예고한 날짜를 먼저 씁니다.
        관찰 노트 회고는 작성 주 + 4주·12주가 지난 다음 월요일 브리핑에 붙습니다. 공시 마감일이 주말이면 실제 마감은 다음 영업일일 수 있습니다.
      </p>
    </div>
  );
}

export default function CalendarPage() {
  return <Suspense fallback={null}><CalendarView /></Suspense>;
}
