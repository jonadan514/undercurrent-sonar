// 사이트 점검(읽기 전용, 2026-11-07) - 새 화면 체크리스트를 실제 데이터로 자동 확인한다(사용자: "체크리스트대로 확인해 봐").
// 기업 카드: 한국어 요약·테마 구간·8분기 표(같은 매출 반복·끝나지 않은 분기·빈 분기)·주의할 사실 / 테마 가치사슬 칸 / 시장 환경 칸 /
// 종목 링크가 기업 카드로 가는지 / 워치리스트 팝업의 카드 링크 / 휴대폰 가로 넘침·콘솔 오류. GET만, 아무것도 쓰지 않는다.
import { chromium } from "playwright";

const BASE = process.env.SITE || "https://u-sonar.vercel.app";
const STOCKS = ["US:MU", "US:KO", "US:AAPL", "US:NVDA", "US:BA", "US:HON", "US:TDG", "US:CCL",
  "KR:005930", "KR:000660", "KR:012450", "KR:042660", "KR:035420", "KR:068270"];
const THEMES = [["defense", "KR"], ["ai_semiconductor", "US"], ["ai_semiconductor", "KR"], ["travel_airline", "US"], ["battery", "KR"], ["specialty_gas", "KR"]];
const LINK_PAGES = ["/briefing", "/radar/theme?id=defense&market=KR", "/investors", "/quarterly", "/scorecard", "/notes", "/"];
const today = new Date().toISOString().slice(0, 10);

const b = await chromium.launch();
async function open(path, W = 1280) {
  const p = await b.newPage({ viewport: { width: W, height: 900 } });
  const errs = [];
  p.on("pageerror", (e) => errs.push("pageerror: " + e.message.slice(0, 140)));
  p.on("console", (m) => m.type() === "error" && errs.push("console: " + m.text().slice(0, 140)));
  p.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 400) errs.push(`API ${r.status()} ${new URL(r.url()).pathname}`); });
  try { await p.goto(BASE + path, { waitUntil: "networkidle", timeout: 60000 }); } catch (e) { errs.push("goto " + e.message.slice(0, 80)); }
  await p.waitForTimeout(1200);
  return { p, errs };
}
const qEnd = (q) => { const [y, n] = q.split("-Q").map(Number); return new Date(Date.UTC(y, n * 3, 0)).toISOString().slice(0, 10); };

console.log("\n######## 1. 기업 카드 ########");
for (const s of STOCKS) {
  const { p, errs } = await open(`/company?stock=${s}`);
  const info = await p.evaluate(() => {
    const main = document.querySelector("main") || document.body;
    const text = main.innerText;
    const h1 = main.querySelector("h1")?.innerText ?? "";
    const sec = [...main.querySelectorAll("section")];
    const first = sec.find((x) => x.innerText.includes("무엇을 하는 회사인가"));
    const summary = first ? (first.querySelector("p.text-\\[13px\\]")?.innerText ?? "") : "";
    const hasKo = /GPT 번역 요약/.test(text);
    const segs = [...text.matchAll(/가치사슬 ([^\n]+?)구간 전체 보기/g)].map((m) => m[1].trim());
    const themes = first ? [...first.querySelectorAll("a[href*='/radar/theme']")].map((a) => a.innerText.trim()) : [];
    const table = [...main.querySelectorAll("table")].find((t) => t.innerText.includes("영업이익률"));
    const rows = table ? [...table.querySelectorAll("tbody tr")].map((tr) => [...tr.querySelectorAll("td")].map((td) => td.innerText.trim())) : [];
    const caut = sec.find((x) => x.innerText.includes("주의할 사실"));
    const cautions = caut ? [...caut.querySelectorAll("li")].map((li) => li.innerText.replace(/\s+/g, " ").slice(0, 70)) : [];
    return { h1, summary: summary.slice(0, 160), hasKo, segs, themes, rows, cautions, len: text.length };
  });
  const probs = [];
  const qs = info.rows.map((r) => r[0]);
  for (let i = 0; i + 1 < info.rows.length; i++) if (info.rows[i][1] !== "-" && info.rows[i][1] === info.rows[i + 1][1]) probs.push(`같은 매출 반복 ${qs[i]}·${qs[i + 1]} ${info.rows[i][1]}`);
  for (const q of qs) if (q.includes("-Q") && qEnd(q) > today) probs.push(`끝나지 않은 분기 ${q}`);
  for (let i = 0; i + 1 < qs.length; i++) {
    const [y, n] = qs[i].split("-Q").map(Number); const [y2, n2] = qs[i + 1].split("-Q").map(Number);
    if ((y * 4 + n) - (y2 * 4 + n2) !== 1) probs.push(`분기 빠짐 ${qs[i + 1]}→${qs[i]}`);
  }
  if (!info.hasKo) probs.push("한국어 요약 없음");
  if (info.themes.length && info.segs.length < info.themes.length) probs.push(`가치사슬 구간 없는 테마 ${info.themes.length - info.segs.length}`);
  console.log(`\n== ${s} ${info.h1} (글자 ${info.len})${probs.length ? "  ⚠️ " + probs.join(" / ") : "  ✓"}`);
  console.log(`  요약: ${info.summary}`);
  console.log(`  테마: ${info.themes.map((t, i) => `${t} [${info.segs[i] ?? "-"}]`).join(" | ") || "없음"}`);
  console.log(`  분기: ${info.rows.map((r) => `${r[0]} ${r[1]}(${r[2]})`).join(" · ")}`);
  console.log(`  주의(${info.cautions.length}): ${info.cautions.join(" / ") || "없음"}`);
  if (errs.length) console.log("  ⚠️ " + [...new Set(errs)].slice(0, 4).join(" / "));
  await p.close();
}

console.log("\n######## 2. 테마 가치사슬 ########");
for (const [id, m] of THEMES) {
  const { p, errs } = await open(`/radar/theme?id=${id}&market=${m}`);
  const groups = await p.evaluate(() => {
    const sec = [...document.querySelectorAll("section")].find((s) => s.querySelector("h2")?.innerText === "가치사슬");
    if (!sec) return null;
    return [...sec.querySelectorAll(":scope div.space-y-2\\.5 > div")].map((g) => {
      const title = g.querySelector("p")?.innerText.replace(/\s+/g, " ") ?? "";
      const names = [...g.querySelectorAll("a")].map((a) => a.innerText.replace(/\s+/g, " ").trim());
      return { title, names };
    });
  });
  console.log(`\n== ${id}(${m})${groups ? "" : "  ⚠️ 가치사슬 칸 없음"}`);
  for (const g of groups || []) console.log(`  ${g.title}: ${g.names.join(", ") || "-"}`);
  if (errs.length) console.log("  ⚠️ " + [...new Set(errs)].slice(0, 4).join(" / "));
  await p.close();
}

console.log("\n######## 3. 시장 환경 ########");
{
  const { p, errs } = await open("/");
  const t = await p.evaluate(() => [...document.querySelectorAll("section")].find((s) => s.querySelector("h2")?.innerText.includes("시장 환경"))?.innerText ?? null);
  console.log(t ? t.replace(/\n{2,}/g, "\n").slice(0, 1500) : "⚠️ 시장 환경 칸 없음");
  if (errs.length) console.log("  ⚠️ " + [...new Set(errs)].slice(0, 4).join(" / "));
  await p.close();
}

console.log("\n######## 4. 종목 링크 ########");
for (const path of LINK_PAGES) {
  const { p, errs } = await open(path);
  const c = await p.evaluate(() => {
    const hs = [...document.querySelectorAll("a[href]")].map((a) => a.getAttribute("href"));
    return { company: hs.filter((h) => h.includes("/company?stock=")).length, wl: hs.filter((h) => h.includes("/watchlist?stock=")).length };
  });
  console.log(`  ${path}: 기업 카드 링크 ${c.company} · 예전 워치리스트 링크 ${c.wl}${c.wl ? "  ⚠️" : ""}${errs.length ? "  ⚠️ " + errs[0] : ""}`);
  await p.close();
}
{
  const { p } = await open("/watchlist");
  const row = p.locator("[role=button]").first();
  let msg = "후보 행 없음";
  if (await row.count()) {
    await row.click(); await p.waitForTimeout(800);
    const link = p.locator("a", { hasText: "기업 카드 전체 보기" });
    msg = (await link.count()) ? `팝업 카드 링크 ✓ ${await link.first().getAttribute("href")}` : "⚠️ 팝업에 기업 카드 링크 없음";
  }
  console.log(`  /watchlist 팝업: ${msg}`);
  await p.close();
}

console.log("\n######## 5. 휴대폰(390) ########");
for (const path of ["/", "/company?stock=KR:005930", "/company?stock=US:MU", "/radar/theme?id=defense&market=KR", "/watchlist", "/briefing"]) {
  const { p, errs } = await open(path, 390);
  const o = await p.evaluate(() => {
    const over = document.documentElement.scrollWidth > window.innerWidth + 1;
    const wide = [...document.querySelectorAll("main *")].filter((e) => {
      const r = e.getBoundingClientRect(); return r.right > window.innerWidth + 2 && getComputedStyle(e).position !== "fixed" && !e.closest(".overflow-x-auto, [style*='overflow']");
    }).slice(0, 3).map((e) => `${e.tagName.toLowerCase()}.${(e.className || "").toString().slice(0, 30)}`);
    return { over, wide };
  });
  console.log(`  ${path}: ${o.over ? "⚠️ 가로 넘침 " + o.wide.join(", ") : "✓"}${errs.length ? "  ⚠️ " + [...new Set(errs)].slice(0, 2).join(" / ") : ""}`);
  await p.close();
}
await b.close();
