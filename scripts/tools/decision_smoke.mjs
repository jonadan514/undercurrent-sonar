// 검토 기록 실제 동작 점검(2026-11-18, 사용자 요청) - 기업 카드에서 사람처럼 눌러 기록하고, 목록에 뜨는지 본 뒤 바로 지운다.
// 남는 것이 없게: 결정 '제외', 출처 '기타', 메모 '자동 점검'으로 적고 같은 날 '지우기'(같은 날 적은 것만 지울 수 있다).
// 지우기에 실패하면 실패로 끝내 사람이 보게 한다. 화면을 JPEG로 찍어 로그에 남긴다(SHOT|...).
import { chromium } from "playwright";

const BASE = process.env.SITE || "https://u-sonar.vercel.app";
const STOCK = process.env.STOCK || "US:ADBE";
const MEMO = "자동 점검 - 곧 지움";
const log = (...a) => console.log(...a);

const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 900 } });
const api = [];
p.on("response", async (r) => {
  if (r.url().includes("/api/decisions")) api.push(`${r.request().method()} ${r.status()} ${new URL(r.url()).search}`);
});
p.on("pageerror", (e) => log("pageerror:", e.message.slice(0, 200)));
let ok = true;
try {
  await p.goto(`${BASE}/company?stock=${encodeURIComponent(STOCK)}`, { waitUntil: "networkidle", timeout: 60000 });
  const panel = p.locator("#decide");
  await panel.scrollIntoViewIfNeeded();
  const before = await panel.innerText();
  log("기록 전 칸 글자 수", before.length, "· 지우기 버튼", await panel.getByRole("button", { name: "지우기" }).count());

  await panel.getByRole("button", { name: "제외", exact: true }).click();
  await panel.getByRole("button", { name: "보통" }).first().click();          // 내가 본 밸류 = 보통
  await panel.getByRole("button", { name: "기타", exact: true }).click();
  await panel.getByPlaceholder(/HBM/).fill(MEMO);
  await panel.getByRole("button", { name: "기록", exact: true }).click();
  await p.getByText("저장했습니다").waitFor({ timeout: 20000 });
  await p.waitForTimeout(1500);
  const row = panel.locator("div", { hasText: MEMO }).last();
  log("기록 뒤 줄:", (await row.innerText()).replace(/\s+/g, " ").slice(0, 200));

  const shot = await p.screenshot({ fullPage: false, type: "jpeg", quality: 60, clip: await panel.boundingBox() });
  const b64 = shot.toString("base64");
  for (let i = 0; i * 60000 < b64.length; i++) console.log(`SHOT|decide|1280|${i}|${b64.slice(i * 60000, (i + 1) * 60000)}`);

  await row.getByRole("button", { name: "지우기" }).click();
  await p.waitForTimeout(3000);
  const left = await panel.getByText(MEMO).count();
  log(left === 0 ? "지우기 확인 - 남은 시험 기록 없음" : `⚠️ 시험 기록이 ${left}줄 남음`);
  if (left) ok = false;
} catch (e) {
  ok = false;
  log("⚠️ 실패:", e.message.slice(0, 300));
}
log("API:", api.join(" | "));
await b.close();
process.exit(ok ? 0 : 1);
