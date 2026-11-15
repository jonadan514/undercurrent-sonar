import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";
import { stockSnapshot, themeSnapshot } from "@/src/lib/stockSnapshot";

export const dynamic = "force-dynamic";

// 관찰 노트 (2026-10-05). 표·규칙은 src/db/observations.py와 같다:
// - 가설과 그때 값(snapshot)은 한 번 쓰면 고치지 않는다. 바꿀 수 있는 건 회고의 판단·배운 점뿐.
// - 4주·12주 회고 값은 scripts/review_observations.py가 주간 계산 직후 채운다.
// - 숫자는 전부 DB 값(그때 값은 작성 순간 DB에 있는 최신 주간 값).

const DDL = [
  `CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, kind TEXT NOT NULL, market TEXT NOT NULL,
    theme_id TEXT, ticker TEXT, hypothesis TEXT NOT NULL, expects TEXT NOT NULL, week_start TEXT NOT NULL,
    snapshot TEXT NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS observation_reviews (
    observation_id INTEGER NOT NULL, checkpoint INTEGER NOT NULL, reviewed_at TEXT NOT NULL, week_start TEXT NOT NULL,
    snapshot TEXT NOT NULL, expect_results TEXT NOT NULL, verdict TEXT, lesson TEXT, judged_at TEXT,
    PRIMARY KEY (observation_id, checkpoint))`,
];
// 축마다 ↑ 또는 ↓ 하나 (earn_hold는 첫 버전 키 - 예전 관찰 읽기용, 새로 받지는 않는다)
const EXPECTS = ["news_up", "news_down", "earn_up", "earn_down", "price_up", "price_down", "unsure"];
const VERDICTS = ["right", "wrong", "unclear"];
const MAX_HYPOTHESIS = 300;

type Client = ReturnType<typeof getClient>;
type Row = Record<string, unknown>;
const objects = (res: { columns: string[]; rows: unknown[][] }): Row[] =>
  res.rows.map((r) => Object.fromEntries(res.columns.map((c, i) => [c, r[i]])));

async function ensure(client: Client) {
  for (const sql of DDL) await client.execute(sql);
}

/** 정기 파이프라인과 같은 "신호 주": 어제가 속한 주의 월요일(src/db/theme_signals.py signal_week_monday). */
function signalWeek(now = new Date()): string {
  const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - 1));
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
}

function parse(row: Row, key: string) {
  try { return JSON.parse((row[key] as string) || "null"); } catch { return null; }
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  try {
    const client = getClient();
    await ensure(client);
    const where: string[] = [];
    const args: string[] = [];
    for (const k of ["theme_id", "ticker", "market", "kind"]) {
      const v = searchParams.get(k);
      if (v) { where.push(`${k} = ?`); args.push(v); }
    }
    const obs = objects(await client.execute({
      sql: `SELECT * FROM observations ${where.length ? "WHERE " + where.join(" AND ") : ""} ORDER BY created_at DESC LIMIT 300`,
      args,
    }) as never);
    const ids = obs.map((o) => o.id as number);
    const reviews: Record<number, Row[]> = {};
    if (ids.length) {
      const rRes = objects(await client.execute({
        sql: `SELECT * FROM observation_reviews WHERE observation_id IN (${ids.map(() => "?").join(",")}) ORDER BY checkpoint`,
        args: ids,
      }) as never);
      rRes.forEach((r) => {
        (reviews[r.observation_id as number] ??= []).push({
          ...r, snapshot: parse(r, "snapshot"), expect_results: parse(r, "expect_results"),
        });
      });
    }
    return NextResponse.json({
      current_week: signalWeek(),
      observations: obs.map((o) => ({
        ...o, expects: parse(o, "expects") ?? [], snapshot: parse(o, "snapshot"), reviews: reviews[o.id as number] ?? [],
      })),
    });
  } catch (err) {
    console.error("[api/notes] GET error:", err);
    return NextResponse.json({ observations: [], current_week: signalWeek() });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const kind = body.kind === "stock" ? "stock" : body.kind === "theme" ? "theme" : null;
    const market = body.market === "KR" ? "KR" : body.market === "US" ? "US" : null;
    const hypothesis = typeof body.hypothesis === "string" ? body.hypothesis.trim().slice(0, MAX_HYPOTHESIS) : "";
    let expects: string[] = Array.isArray(body.expects) ? body.expects.filter((e: unknown) => EXPECTS.includes(e as string)) : [];
    // 같은 축의 ↑와 ↓를 동시에 고를 수 없다 - 둘 다 오면 그 축은 버린다
    for (const ax of ["news", "earn", "price"]) {
      if (expects.includes(`${ax}_up`) && expects.includes(`${ax}_down`)) expects = expects.filter((e) => !e.startsWith(`${ax}_`));
    }
    if (expects.includes("unsure")) expects = ["unsure"];
    const themeId = kind === "theme" && typeof body.theme_id === "string" ? body.theme_id : null;
    const ticker = kind === "stock" && typeof body.ticker === "string" ? body.ticker.trim().toUpperCase() : null;
    if (!kind || !market || !hypothesis || (kind === "theme" && !themeId) || (kind === "stock" && !ticker)) {
      return NextResponse.json({ error: "대상·시장·가설이 필요합니다" }, { status: 400 });
    }
    const client = getClient();
    await ensure(client);
    const snapshot = kind === "theme" ? await themeSnapshot(client, themeId!, market) : await stockSnapshot(client, ticker!, market);
    if (kind === "theme" && !snapshot) {
      return NextResponse.json({ error: "이 테마의 주간 신호가 아직 없습니다" }, { status: 400 });
    }
    const res = await client.execute({
      sql: `INSERT INTO observations (created_at, kind, market, theme_id, ticker, hypothesis, expects, week_start, snapshot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      args: [new Date().toISOString(), kind, market, themeId, ticker, hypothesis, JSON.stringify(expects),
             signalWeek(), JSON.stringify(snapshot)],
    });
    return NextResponse.json({ ok: true, id: Number(res.lastInsertRowid ?? 0), snapshot });
  } catch (err) {
    console.error("[api/notes] POST error:", err);
    return NextResponse.json({ error: "저장 실패" }, { status: 500 });
  }
}

// 회고 판단·배운 점만 바꿀 수 있다(가설·그때 값·지금 값은 그대로).
export async function PATCH(request: Request) {
  try {
    const body = await request.json();
    const id = Number(body.observation_id), cp = Number(body.checkpoint);
    const verdict = VERDICTS.includes(body.verdict) ? body.verdict : null;
    const lesson = typeof body.lesson === "string" ? body.lesson.trim().slice(0, MAX_HYPOTHESIS) : null;
    if (!id || ![4, 12].includes(cp)) return NextResponse.json({ error: "잘못된 요청" }, { status: 400 });
    const client = getClient();
    await ensure(client);
    const res = await client.execute({
      sql: `UPDATE observation_reviews SET verdict = ?, lesson = ?, judged_at = ? WHERE observation_id = ? AND checkpoint = ?`,
      args: [verdict, lesson || null, new Date().toISOString(), id, cp],
    });
    if (!res.rowsAffected) return NextResponse.json({ error: "아직 회고가 없습니다" }, { status: 404 });
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/notes] PATCH error:", err);
    return NextResponse.json({ error: "저장 실패" }, { status: 500 });
  }
}

// 잘못 적은 관찰 지우기 - 회고가 하나도 붙기 전에만. 회고가 붙은 뒤에는 기록으로 남긴다.
export async function DELETE(request: Request) {
  const id = Number(new URL(request.url).searchParams.get("id"));
  if (!id) return NextResponse.json({ error: "id 필요" }, { status: 400 });
  try {
    const client = getClient();
    await ensure(client);
    const r = await client.execute({ sql: "SELECT COUNT(*) FROM observation_reviews WHERE observation_id = ?", args: [id] });
    if (Number(r.rows[0]?.[0] ?? 0) > 0) {
      return NextResponse.json({ error: "회고가 붙은 관찰은 지울 수 없습니다" }, { status: 409 });
    }
    await client.execute({ sql: "DELETE FROM observations WHERE id = ?", args: [id] });
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/notes] DELETE error:", err);
    return NextResponse.json({ error: "삭제 실패" }, { status: 500 });
  }
}
