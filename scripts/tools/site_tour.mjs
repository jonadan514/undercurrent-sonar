// 사이트 둘러보기(읽기 전용, 2026-11-05). 페이지마다 제목·섹션 머리·빈 칸/오류 문구·콘솔 오류·실패한 API 요청을 텍스트로 찍는다.
// 작업 환경에서 사이트에 바로 닿지 않아 Actions에서 돌린다. 아무것도 쓰지 않는다(GET만).
import { chromium } from "playwright";

const BASE = process.env.SITE || "https://u-sonar.vercel.app";
const PAGES = ["/", "/radar", "/radar/theme?id=lng_gas&market=US", "/sector", "/briefing", "/quarterly", "/watchlist",
  "/investors", "/notes", "/scorecard", "/status", "/guide", "/guide/detail", "/guide/playbook"];
const EMPTY = /데이터 없음|없습니다|불러오지|오류|실패|Error|error|준비 중|아직 없|no data/i;

const b = await chromium.launch();
for (const W of [1280, 390]) {
  for (const path of PAGES) {
    const p = await b.newPage({ viewport: { width: W, height: 900 } });
    const errs = [], bad = [];
    p.on("pageerror", (e) => errs.push("pageerror: " + e.message.slice(0, 160)));
    p.on("console", (m) => m.type() === "error" && errs.push("console: " + m.text().slice(0, 160)));
    p.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 400) bad.push(`${r.status()} ${new URL(r.url()).pathname}`); });
    const t0 = Date.now();
    try { await p.goto(BASE + path, { waitUntil: "networkidle", timeout: 60000 }); } catch (e) { errs.push("goto: " + e.message.slice(0, 120)); }
    await p.waitForTimeout(1500);
    const info = await p.evaluate((emptyRe) => {
      const re = new RegExp(emptyRe, "i");
      const main = document.querySelector("main") || document.body;
      const heads = [...main.querySelectorAll("h1,h2,h3")].map((h) => h.innerText.trim().replace(/\s+/g, " ")).filter(Boolean);
      const empties = [...main.querySelectorAll("p,div,span,td")].filter((e) => e.children.length === 0 && re.test(e.innerText || ""))
        .map((e) => e.innerText.trim().replace(/\s+/g, " ").slice(0, 90));
      const sc = [...document.querySelectorAll("main, body > div, body > div > div")].reduce((m, e) => Math.max(m, e.scrollHeight), document.body.scrollHeight);
      const overflow = document.documentElement.scrollWidth > window.innerWidth + 1;
      return { heads, empties: [...new Set(empties)].slice(0, 12), height: sc, overflow, chars: (main.innerText || "").length };
    }, EMPTY.source);
    if (W === 1280) {
      console.log(`\n=== ${path}  (${Date.now() - t0}ms, 높이 ${info.height}px, 글자 ${info.chars})`);
      console.log("  머리: " + info.heads.slice(0, 40).join(" | "));
      if (info.empties.length) console.log("  빈칸/오류 문구: " + info.empties.join(" / "));
    } else if (info.overflow || errs.length || bad.length) {
      console.log(`\n--- 모바일 ${path}${info.overflow ? "  ⚠️가로 넘침" : ""}`);
    }
    if (errs.length) console.log("  ⚠️ " + [...new Set(errs)].slice(0, 6).join("\n  ⚠️ "));
    if (bad.length) console.log("  ⚠️ API 실패: " + [...new Set(bad)].join(", "));
    await p.close();
  }
}
await b.close();
