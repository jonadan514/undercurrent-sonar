import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 데이터 상태 한눈에 보기(2026-10-21). 정기 수집이 10개 넘게 늘어 어떤 칸이 오래된 데이터인지 바로 보이게.
// GitHub 실행 기록이 아니라 각 표의 마지막 저장 시각으로 본다 - 토큰이 필요 없고(공개 저장소라 실행 링크·토큰을 화면에 두지 않는다),
// "실행은 성공했는데 저장이 안 된" 경우도 잡힌다. GitHub 예약 실행은 몇 시간씩 늦게 시작돼서 허용 기간에 여유를 둔다.
type Source = { key: string; label: string; group: "매일" | "매주" | "분기"; cadence: string; okDays: number; sql: string; note?: string };

const SOURCES: Source[] = [
  { key: "macro", label: "매크로 지표", group: "매일", cadence: "매일 아침", okDays: 3, sql: "SELECT MAX(updated_at) FROM macro_snapshot" },
  { key: "kr_rates", label: "국고채 금리", group: "매일", cadence: "거래일", okDays: 4, sql: "SELECT MAX(date) FROM kr_rates", note: "데이터 날짜(주말·휴일 제외)" },
  { key: "kr_flows", label: "코스피·코스닥 수급", group: "매일", cadence: "거래일", okDays: 4, sql: "SELECT MAX(date) FROM kr_investor_flows", note: "데이터 날짜(주말·휴일 제외)" },
  { key: "kr_disclosures", label: "한국 공시", group: "매일", cadence: "매일 밤", okDays: 3, sql: "SELECT MAX(fetched_at) FROM kr_disclosures" },
  { key: "insider_us", label: "내부자 매수 · 미국", group: "매일", cadence: "매일 밤", okDays: 3, sql: "SELECT MAX(checked_at) FROM insider_filings_seen WHERE market = 'US'", note: "새로 읽은 Form 4가 있을 때만 시각이 바뀐다" },
  { key: "insider_kr", label: "내부자 매수 · 한국", group: "매일", cadence: "매일 밤", okDays: 4, sql: "SELECT MAX(checked_at) FROM insider_filings_seen WHERE market = 'KR'", note: "새로 읽은 보고서가 있을 때만 시각이 바뀐다" },
  { key: "us_8k", label: "미국 8-K", group: "매일", cadence: "매일 밤", okDays: 4, sql: "SELECT MAX(fetched_at) FROM us_8k_filings", note: "새 8-K가 있을 때만 시각이 바뀐다" },
  { key: "theme_events", label: "테마 이벤트(공시·내부자)", group: "매일", cadence: "매일 밤", okDays: 3, sql: "SELECT MAX(computed_at) FROM theme_events" },
  { key: "watchlist", label: "워치리스트 스크리닝", group: "매주", cadence: "월요일 아침", okDays: 9, sql: "SELECT MAX(screened_at) FROM watchlist_screening_results" },
  { key: "narratives", label: "네러티브 브리프", group: "매주", cadence: "월요일 아침", okDays: 9, sql: "SELECT MAX(updated_at) FROM narrative_briefs" },
  { key: "briefing", label: "주간 브리핑", group: "매주", cadence: "월요일 아침", okDays: 9, sql: "SELECT MAX(created_at) FROM weekly_briefings" },
  // theme_news_weekly는 과거 백필(건수만) 표라 정기 수집이 쓰지 않는다 - 정기 수집이 채우는 theme_signals 뉴스 칸으로 본다(2026-10-25)
  { key: "theme_news", label: "테마 뉴스", group: "매주", cadence: "월요일 아침", okDays: 15, sql: "SELECT MAX(week_start) FROM theme_signals WHERE news_count IS NOT NULL", note: "측정한 주의 월요일 날짜 - 실행은 그 주 일요일 밤이라 다음 실행 직전엔 13일쯤" },
  { key: "radar_us", label: "테마 레이더 · 미국", group: "매주", cadence: "월요일 아침", okDays: 15, sql: "SELECT MAX(week_start) FROM theme_signals WHERE market = 'US'", note: "측정한 주의 월요일 날짜 - 실행은 그 주 일요일 밤이라 다음 실행 직전엔 13일쯤" },
  { key: "radar_kr", label: "테마 레이더 · 한국", group: "매주", cadence: "월요일 아침", okDays: 15, sql: "SELECT MAX(week_start) FROM theme_signals WHERE market = 'KR'", note: "측정한 주의 월요일 날짜 - 실행은 그 주 일요일 밤이라 다음 실행 직전엔 13일쯤" },
  { key: "sector_us", label: "섹터 분석 · 미국", group: "매주", cadence: "화요일 아침", okDays: 9, sql: "SELECT MAX(updated_at) FROM sector_analysis" },
  { key: "sector_kr", label: "섹터 분석 · 한국", group: "매주", cadence: "화요일 아침", okDays: 9, sql: "SELECT MAX(updated_at) FROM kr_sector_analysis" },
  { key: "earnings", label: "실적 발표일", group: "매주", cadence: "월요일 새벽", okDays: 9, sql: "SELECT MAX(fetched_at) FROM earnings_calendar" },
  { key: "scorecard", label: "성적표(후보 수익률)", group: "매주", cadence: "월요일 아침", okDays: 9, sql: "SELECT MAX(updated_at) FROM data_pick_returns" },
  { key: "signals", label: "신호 사후 확인", group: "매주", cadence: "월요일 아침", okDays: 9, sql: "SELECT MAX(logged_at) FROM signal_log" },
  { key: "quarterly", label: "분기 리서치", group: "분기", cadence: "분기 재무 공시 뒤", okDays: 110, sql: "SELECT MAX(computed_at) FROM quarterly_theme_classification" },
];

// '2026-10-21 03:45:00'(SQLite datetime, UTC) · ISO · '2026-10-21'(날짜만) 모두 받는다. 날짜만이면 그날 0시(UTC)로.
function parseTime(v: unknown): number | null {
  if (v == null) return null;
  const s = String(v).trim();
  if (!s) return null;
  const iso = /^\d{4}-\d{2}-\d{2}$/.test(s) ? `${s}T00:00:00Z` : /[zZ]|[+-]\d{2}:?\d{2}$/.test(s) ? s.replace(" ", "T") : `${s.replace(" ", "T")}Z`;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

export async function GET() {
  const now = Date.now();
  // DB 연결 자체가 안 되면(설정 누락 등) 500 대신 전부 '없음'으로 - 사이드바가 "없음 20"을 보여 문제를 바로 알린다
  let results: PromiseSettledResult<{ rows: unknown[][] }>[];
  try {
    const client = getClient();
    results = await Promise.allSettled(SOURCES.map((s) => client.execute(s.sql) as unknown as Promise<{ rows: unknown[][] }>));
  } catch {
    results = SOURCES.map(() => ({ status: "rejected", reason: "db" }) as PromiseRejectedResult);
  }
  const items = SOURCES.map((s, i) => {
    const r = results[i];
    const raw = r.status === "fulfilled" ? r.value.rows[0]?.[0] ?? null : null;
    const t = parseTime(raw);
    const ageDays = t == null ? null : (now - t) / 86_400_000;
    const status = t == null ? "missing" : ageDays! > s.okDays ? "late" : "ok";
    return { key: s.key, label: s.label, group: s.group, cadence: s.cadence, ok_days: s.okDays, note: s.note ?? null,
             last: t == null ? null : new Date(t).toISOString(), age_days: ageDays == null ? null : Math.round(ageDays * 10) / 10, status };
  });
  const summary = { total: items.length, ok: items.filter((x) => x.status === "ok").length,
                    late: items.filter((x) => x.status === "late").length, missing: items.filter((x) => x.status === "missing").length };
  return NextResponse.json({ checked_at: new Date(now).toISOString(), summary, items });
}
