import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";
import { stockSnapshot } from "@/src/lib/stockSnapshot";

export const dynamic = "force-dynamic";

// 검토 기록(2026-11-15, 사용자: 3개월 가상 매수 검증). 종목을 보고 관심·보류·제외 중 하나를 누른 기록.
// - 덮어쓰지 않는다(원칙 5): 생각이 바뀌면 새 줄. 지우기는 같은 날(한국 시간) 적은 줄만 - 잘못 누른 것 바로잡기용.
// - 그때 값(snapshot)은 서버가 DB에서 읽어 붙인다(원칙 2). 내 확인(밸류·실적·차트)은 사용자가 고른 것 그대로.
// - 결과(4·12·26주 수익률, TIGER 반도체TOP10·지수 대비)는 scripts/compute_decision_outcomes.py가 stock_decision_outcomes에 채운다.
// 점수·순위는 만들지 않는다(원칙 1) - 결정과 그 뒤 사실만.

const DDL = `CREATE TABLE IF NOT EXISTS stock_decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  decided_on TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT,
  decision TEXT NOT NULL,
  checks TEXT NOT NULL,
  source TEXT NOT NULL,
  memo TEXT,
  snapshot TEXT NOT NULL
)`;
const DECISIONS = ["watch", "hold", "pass"];
const CHECK_KEYS = ["value", "earn", "chart"];
const CHECK_VALUES = ["good", "mid", "bad"];
const SOURCES = ["tool", "blog", "other"];
const MAX_MEMO = 200;

type Row = Record<string, unknown>;
const objects = (res: { columns: string[]; rows: unknown[][] }): Row[] =>
  res.rows.map((r) => Object.fromEntries(res.columns.map((c, i) => [c, r[i]])));
const parse = (v: unknown) => { try { return JSON.parse(String(v ?? "null")); } catch { return null; } };
/** 한국 시간 날짜 - 결과 계산은 이 날짜 '다음' 첫 거래일 종가에서 시작한다(본 가격은 그 전 종가라서). */
const kstDate = (d = new Date()) => new Date(d.getTime() + 9 * 3600e3).toISOString().slice(0, 10);

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  try {
    const client = getClient();
    await client.execute(DDL);
    const where: string[] = [], args: string[] = [];
    for (const k of ["market", "symbol"]) {
      const v = searchParams.get(k);
      if (v) { where.push(`d.${k} = ?`); args.push(k === "symbol" ? v.toUpperCase() : v); }
    }
    const base = `SELECT d.* FROM stock_decisions d ${where.length ? "WHERE " + where.join(" AND ") : ""} ORDER BY d.created_at DESC LIMIT 1000`;
    const rows = objects(await client.execute({ sql: base, args }) as never);
    // 결과 표는 결과 계산이 처음 돈 뒤에 생긴다 - 없으면 결과 없이
    let outs: Record<number, Row> = {};
    try {
      const o = objects(await client.execute("SELECT * FROM stock_decision_outcomes") as never);
      outs = Object.fromEntries(o.map((r) => [Number(r.decision_id), r]));
    } catch { /* 아직 없음 */ }
    return NextResponse.json({
      today: kstDate(),
      decisions: rows.map((r) => ({ ...r, checks: parse(r.checks) ?? {}, snapshot: parse(r.snapshot), outcome: outs[Number(r.id)] ?? null })),
    });
  } catch (err) {
    console.error("[api/decisions] GET error:", err);
    return NextResponse.json({ today: kstDate(), decisions: [] });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const market = body.market === "KR" ? "KR" : body.market === "US" ? "US" : null;
    const symbol = typeof body.symbol === "string" ? body.symbol.trim().toUpperCase() : "";
    const decision = DECISIONS.includes(body.decision) ? body.decision : null;
    const source = SOURCES.includes(body.source) ? body.source : null;
    if (!market || !symbol || !decision || !source) return NextResponse.json({ error: "종목·결정·출처가 필요합니다" }, { status: 400 });
    const checks: Record<string, string> = {};
    for (const k of CHECK_KEYS) if (CHECK_VALUES.includes(body.checks?.[k])) checks[k] = body.checks[k];
    const memo = typeof body.memo === "string" ? body.memo.trim().slice(0, MAX_MEMO) : "";
    const name = typeof body.name === "string" ? body.name.slice(0, 80) : null;

    const client = getClient();
    await client.execute(DDL);
    const snap: Row = await stockSnapshot(client, symbol, market);
    // 재무 필터 판정(후보가 아니어도 있는 값) - 통과/탈락/데이터 부족 그대로(원칙 4)
    try {
      const s = objects(await client.execute({
        sql: "SELECT status, piotroski FROM watchlist_screening_results WHERE market = ? AND symbol = ?", args: [market, symbol],
      }) as never)[0];
      if (s) Object.assign(snap, { screen_status: s.status, screen_piotroski: s.piotroski });
    } catch { /* 표 없음 */ }
    // 차트 상태(stock_price_facts, 매일 계산) - 있으면 그때 값으로
    try {
      const f = objects(await client.execute({
        sql: "SELECT as_of, close, pos_52w, above_ma200, ret_3m FROM stock_price_facts WHERE market = ? AND symbol = ?", args: [market, symbol],
      }) as never)[0];
      if (f) snap.chart = f;
    } catch { /* 표 없음 */ }

    const res = await client.execute({
      sql: `INSERT INTO stock_decisions (created_at, decided_on, market, symbol, name, decision, checks, source, memo, snapshot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      args: [new Date().toISOString(), kstDate(), market, symbol, name, decision, JSON.stringify(checks), source, memo || null, JSON.stringify(snap)],
    });
    return NextResponse.json({ ok: true, id: Number(res.lastInsertRowid ?? 0) });
  } catch (err) {
    console.error("[api/decisions] POST error:", err);
    return NextResponse.json({ error: "저장 실패" }, { status: 500 });
  }
}

// 잘못 누른 기록 지우기 - 같은 날(한국 시간) 적은 것만. 하루가 지나면 기록으로 남긴다.
export async function DELETE(request: Request) {
  const id = Number(new URL(request.url).searchParams.get("id"));
  if (!id) return NextResponse.json({ error: "id 필요" }, { status: 400 });
  try {
    const client = getClient();
    await client.execute(DDL);
    const r = await client.execute({ sql: "DELETE FROM stock_decisions WHERE id = ? AND decided_on = ?", args: [id, kstDate()] });
    if (!r.rowsAffected) return NextResponse.json({ error: "오늘 적은 기록만 지울 수 있습니다" }, { status: 409 });
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/decisions] DELETE error:", err);
    return NextResponse.json({ error: "지우기 실패" }, { status: 500 });
  }
}
