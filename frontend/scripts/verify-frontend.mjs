/** Real-browser smoke test for the Next.js consoles. */
import { chromium } from "playwright";

const baseUrl = "http://localhost:3000";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => {
  if (m.type() === "error") errors.push(`console: ${m.text()}`);
});

try {
  // 1. Open /portal without identity -> inline identity picker is shown
  await page.goto(`${baseUrl}/portal`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("text=选择开发环境身份", { timeout: 20000 });
  console.log("PASS: no identity renders inline identity picker");

  // 2. Picker renders tenant list
  await page.waitForSelector("text=synthetic-1", { timeout: 20000 });
  console.log("PASS: identity picker renders tenants");

  // 3. Expand synthetic-1, pick a customer user, expect the portal to appear
  await page.click("text=synthetic-1", { timeout: 20000 });
  await page.waitForSelector("text=客户用户1", { timeout: 20000 });
  await page.click("text=客户用户1");
  await page.waitForSelector("text=我的工单", { timeout: 20000 });
  console.log("PASS: selected identity shows portal");

  // 4. Portal overview renders with ticket data
  await page.waitForSelector("text=客户门户", { timeout: 20000 });
  await page.waitForSelector("text=我的工单", { timeout: 20000 });
  console.log("PASS: portal overview rendered");
  await page.screenshot({ path: "scripts/verify-portal.png", fullPage: true });

  // 5. Portal consult page with SSE flow
  await page.goto(`${baseUrl}/portal/consult`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("text=提交问题", { timeout: 20000 });
  await page.locator("textarea").first().fill("I was charged twice this month, please check.");
  await page.click('button:has-text("提交")', { timeout: 10000 });
  await page.waitForSelector("text=处理进度", { timeout: 30000 });
  await page.waitForSelector("text=处理完成", { timeout: 30000 });
  console.log("PASS: portal consult SSE stream rendered");
  await page.screenshot({ path: "scripts/verify-consult.png", fullPage: true });

  // 6. Navigate via the top bar to the workspace and admin consoles
  await page.click("text=客服工作台", { timeout: 20000 });
  await page.waitForSelector("text=工单队列", { timeout: 20000 });
  console.log("PASS: workspace ticket queue rendered");

  await page.click("text=管理控制台", { timeout: 20000 });
  await page.waitForSelector("text=管理控制台", { timeout: 20000 });
  await page.waitForSelector("text=后端服务", { timeout: 20000 });
  console.log("PASS: admin overview rendered");
} catch (err) {
  console.error("FAIL:", err.message);
  await page.screenshot({ path: "scripts/verify-fail.png", fullPage: true }).catch(() => {});
  process.exitCode = 1;
} finally {
  if (errors.length) {
    console.log("BROWSER ERRORS:");
    for (const e of errors.slice(0, 8)) console.log("  ", e);
  } else {
    console.log("No browser console/page errors");
  }
  await browser.close();
}
