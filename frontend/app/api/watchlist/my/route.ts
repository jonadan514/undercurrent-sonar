import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

async function ensureTable() {
  const client = getClient();
  await client.execute(`
    CREATE TABLE IF NOT EXISTS my_watchlist (
      id       INTEGER PRIMARY KEY AUTOINCREMENT,
      market   TEXT NOT NULL,
      symbol   TEXT NOT NULL,
      name     TEXT,
      note     TEXT,
      added_at TEXT NOT NULL DEFAULT (datetime('now')),
      UNIQUE(market, symbol)
    )
  `);
  // 메모 수정 이력 — 덮어쓰기 전 값을 append로 보존 (사후 확신 편향 방지, stock_checklist_history와 동일 취지)
  await client.execute(`
    CREATE TABLE IF NOT EXISTS my_watchlist_note_history (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      market      TEXT NOT NULL,
      symbol      TEXT NOT NULL,
      note        TEXT,
      recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
  `);
  // 보유 기록 3칸 — 나중에 붙인 컬럼이라 ALTER TABLE을 try/catch로 감싼다
  // (CREATE TABLE IF NOT EXISTS는 이미 있는 표에 컬럼을 더해주지 않는다.
  //  compute_watchlist_valuation.py의 LATE_COLUMNS와 같은 방식).
  //
  // 이건 "내가 산 것"을 적어두는 기록이지 매수 판정이 아니다. 수익률도 순위도
  // 만들지 않는다 - 분기 점검 때 "적어둔 조건이 현실이 됐나"만 묻는 용도다
  // (리서치 실행 가이드 4단계).
  for (const col of ["bought_at TEXT", "buy_price REAL", "thesis_breaks TEXT"]) {
    try {
      await client.execute(`ALTER TABLE my_watchlist ADD COLUMN ${col}`);
    } catch {
      // 이미 있는 컬럼 — 정상
    }
  }
  return client;
}

// 요청에 키가 **있을 때만** 해당 칸을 건드린다.
// 워치리스트의 "+ 추가" 버튼은 market/symbol/name만 보내는데, 그걸로 이미 적어둔
// 매수가·깨지는 조건이 지워지면 안 된다. 반대로 값을 비우고 싶을 때는 null을
// 명시적으로 보내면 지워진다.
const OPTIONAL_COLS = ["note", "bought_at", "buy_price", "thesis_breaks"] as const;

export async function GET() {
  try {
    const client = await ensureTable();
    const res = await client.execute("SELECT * FROM my_watchlist ORDER BY added_at DESC");
    const rows = res.rows.map((r: any) => {
      const obj: Record<string, unknown> = {};
      res.columns.forEach((col, i) => { obj[col] = r[i]; });
      return obj;
    });
    return NextResponse.json(rows);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { market, symbol, name } = body;
    if (!market || !symbol) {
      return NextResponse.json({ error: "market, symbol 필수" }, { status: 400 });
    }
    const client = await ensureTable();
    const upperSymbol = symbol.toUpperCase();

    // 이번 요청이 실제로 건드리는 칸만 고른다(위 OPTIONAL_COLS 주석 참고).
    const touched = OPTIONAL_COLS.filter((c) => c in body);

    const insertCols = ["market", "symbol", "name", ...touched];
    const insertArgs = [market, upperSymbol, name ?? null, ...touched.map((c) => body[c] ?? null)];
    const updateSet = ["name=excluded.name", ...touched.map((c) => `${c}=excluded.${c}`)].join(", ");

    await client.execute({
      sql: `INSERT INTO my_watchlist (${insertCols.join(", ")})
            VALUES (${insertCols.map(() => "?").join(", ")})
            ON CONFLICT(market, symbol) DO UPDATE SET ${updateSet}`,
      args: insertArgs,
    });

    // 메모를 실제로 바꾼 요청만 이력에 남긴다 - 매수가만 고친 요청이 메모 이력을
    // 같은 값으로 한 줄 더 쌓으면 "언제 생각이 바뀌었나"를 읽기 어려워진다.
    if ("note" in body) {
      await client.execute({
        sql: `INSERT INTO my_watchlist_note_history (market, symbol, note) VALUES (?, ?, ?)`,
        args: [market, upperSymbol, body.note ?? null],
      });
    }
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
