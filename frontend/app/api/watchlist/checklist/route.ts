import { NextResponse } from "next/server";
import { getClient } from "@/src/lib/db";

export const dynamic = "force-dynamic";

// 종목별 정성 체크리스트 — 워치리스트 상세 팝업에 흡수된 워크북 기능.
// 전역 상태였던 옛 workbook_checklist와 달리 (market, symbol)별로 독립 저장된다.
//
// 2026-09-07: 5개 -> 3개로 축소. 뺀 두 항목은 화면이 이미 자동으로 보여주는 것을
// 사람에게 다시 묻고 있었다:
//   - "6개월 내 촉매가 있는가?" -> 내러티브 브리프의 "다가오는 촉매"가 바로 위에 있음
//   - "관심도가 상승 중인가?"   -> HOT/WARM/COLD 배지와 상승 전환 배지가 자동 계산됨.
//     게다가 가이드는 관심도를 "보조 정보일 뿐 핵심 지표 아님"이라 설명하는데
//     체크 항목으로 두면 판단 기준처럼 보여 자기 모순이었다.
// 2026-11-11: 내러티브 브리프의 스토리·촉매·리스크 문장을 화면에서 뺐다 - 첫 질문은 회사 소개·테마 근거·숫자를 보고 답한다.
// 남긴 3개는 이 도구가 "시스템이 대신 판단할 수 없다"고 반복해서 말하는 질문들이다.
const DEFAULT_ITEMS = [
  { id: "cl-story",    text: "회사 소개·테마 근거·숫자를 보고, 이 종목의 스토리를 한 문장으로 말할 수 있는가?", checked: false },
  { id: "cl-risk",     text: "스토리가 깨지는 조건을 알고 있는가?", checked: false },
  { id: "cl-durable",  text: "이 스토리가 1년 후에도 유효할 것 같은가? (일시적 이슈가 아닌 구조적 동력인지)", checked: false },
];
const ITEM_IDS = DEFAULT_ITEMS.map((it) => it.id);

async function ensureTable() {
  const client = getClient();
  await client.execute(`
    CREATE TABLE IF NOT EXISTS stock_checklist (
      market     TEXT NOT NULL,
      symbol     TEXT NOT NULL,
      items      TEXT NOT NULL DEFAULT '[]',
      updated_at TEXT NOT NULL DEFAULT (datetime('now')),
      PRIMARY KEY (market, symbol)
    )
  `);
  // 체크리스트는 언제든 다시 수정 가능하지만(진행 중 모니터링 용도), 그 변경 자체는
  // 덮어쓰지 않고 append로 남긴다 — 사후 확신 편향으로 과거 판단을 조용히 고쳐 쓰는 것 방지.
  await client.execute(`
    CREATE TABLE IF NOT EXISTS stock_checklist_history (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      market      TEXT NOT NULL,
      symbol      TEXT NOT NULL,
      items       TEXT NOT NULL,
      recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
  `);
  return client;
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const market = (searchParams.get("market") ?? "").toUpperCase();
    const symbol = (searchParams.get("symbol") ?? "").toUpperCase();
    if (!market || !symbol) {
      return NextResponse.json({ error: "market, symbol 필수" }, { status: 400 });
    }
    const client = await ensureTable();
    const res = await client.execute({
      sql: "SELECT items FROM stock_checklist WHERE market = ? AND symbol = ?",
      args: [market, symbol],
    });
    // 저장된 값이 있어도 항목 구성은 항상 현재 DEFAULT_ITEMS 기준으로 맞춘다
    // (체크 상태만 이어받음) - 항목을 줄이거나 문구를 고쳤을 때 이미 저장된
    // 종목만 옛 항목을 계속 보여주는 문제를 막기 위함. 원본 이력은
    // stock_checklist_history에 그대로 남아 있다.
    const row = res.rows[0];
    let checkedById: Record<string, boolean> = {};
    if (row) {
      try {
        const parsed = JSON.parse(row[0] as string);
        if (Array.isArray(parsed)) {
          for (const it of parsed) {
            if (it && typeof it.id === "string" && ITEM_IDS.includes(it.id)) {
              checkedById[it.id] = Boolean(it.checked);
            }
          }
        }
      } catch {}
    }
    const items = DEFAULT_ITEMS.map((it) => ({ ...it, checked: checkedById[it.id] ?? false }));
    return NextResponse.json({ items });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const { market, symbol, items } = await request.json();
    if (!market || !symbol || !Array.isArray(items)) {
      return NextResponse.json({ error: "market, symbol, items 필수" }, { status: 400 });
    }
    const client = await ensureTable();
    const upperMarket = market.toUpperCase();
    const upperSymbol = symbol.toUpperCase();
    const itemsJson = JSON.stringify(items);
    await client.execute({
      sql: `INSERT INTO stock_checklist (market, symbol, items, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(market, symbol) DO UPDATE SET
              items = excluded.items, updated_at = excluded.updated_at`,
      args: [upperMarket, upperSymbol, itemsJson],
    });
    await client.execute({
      sql: `INSERT INTO stock_checklist_history (market, symbol, items) VALUES (?, ?, ?)`,
      args: [upperMarket, upperSymbol, itemsJson],
    });
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
