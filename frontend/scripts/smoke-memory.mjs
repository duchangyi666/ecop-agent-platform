import { chromium } from "playwright";

const baseUrl = process.env.SMOKE_BASE_URL ?? "http://127.0.0.1:3000";
if (!["localhost", "127.0.0.1", "::1"].includes(new URL(baseUrl).hostname)) throw new Error("Memory smoke requires local frontend");
const tenant = process.env.SMOKE_TENANT_SLUG ?? "clouddesk-demo";
const marker = `memory-smoke-${Date.now().toString(36)}`;
const browser = await chromium.launch();
const page = await browser.newPage();
page.setDefaultTimeout(30000);
let headers;
async function identity(email) {
  await page.goto(`${baseUrl}/identity`);
  await page.getByRole("button", { name: new RegExp(`^${tenant} `) }).click();
  await page.getByRole("button", { name: new RegExp(email.replaceAll(".", "\\.")) }).click();
  await page.waitForURL("**/chat");
}
try {
  await identity("customer@clouddesk.demo");
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("clouddesk-identity")).state.identity);
  headers = { "X-Tenant-Id": stored.tenantId, "X-Actor-Id": stored.userId, "X-Actor-Type": "user" };
  await page.request.patch(`${baseUrl}/api/v1/memories/settings/current`, { headers, data: { enabled: true } });
  const seed = await page.request.post(`${baseUrl}/api/v1/customer-consultations`, { headers, data: { thread_id: marker, message: `客户咨询，我偏好${marker}` } });
  if (!seed.ok()) throw new Error(`Memory seed failed: ${seed.status()}`);
  await page.getByRole("link", { name: "我的记忆", exact: true }).click();
  let row = page.getByRole("listitem").filter({ hasText: marker });
  await row.waitFor();
  page.once("dialog", (dialog) => dialog.accept(`${marker}-corrected`));
  await row.getByRole("button", { name: "修改", exact: true }).click();
  await page.getByRole("status").filter({ hasText: "记忆已更新" }).waitFor();
  row = page.getByRole("listitem").filter({ hasText: `${marker}-corrected` });
  await row.waitFor();
  const toggle = page.getByRole("checkbox", { name: "启用长期记忆" });
  const saved = page.waitForResponse((response) => response.url().endsWith("/memories/settings/current") && response.request().method() === "PATCH");
  await toggle.click();
  if (!(await saved).ok()) throw new Error("Could not disable memory");
  await page.reload();
  await row.waitFor();
  if (await toggle.isChecked()) throw new Error("Memory opt-out did not persist");
  if (await row.getByRole("button", { name: "修改", exact: true }).isEnabled()) throw new Error("Correction enabled while memory disabled");
  page.once("dialog", (dialog) => dialog.accept());
  await row.getByRole("button", { name: "删除", exact: true }).click();
  await page.getByRole("status").filter({ hasText: "记忆已删除" }).waitFor();
  if (await page.getByRole("listitem").filter({ hasText: marker }).count()) throw new Error("Deleted memory still visible");
  await identity("guest@clouddesk.demo");
  await page.goto(`${baseUrl}/memories`);
  await page.getByText("当前身份没有记忆管理权限", { exact: true }).waitFor();
  if (await page.getByRole("listitem").filter({ hasText: marker }).count()) throw new Error("Prior identity memory leaked");
  console.log("PASS: memory correction, opt-out persistence, deletion and identity isolation");
} finally {
  if (headers) {
    await page.request.patch(`${baseUrl}/api/v1/memories/settings/current`, { headers, data: { enabled: true } });
    const result = await page.request.get(`${baseUrl}/api/v1/memories?limit=100`, { headers });
    if (result.ok()) for (const memory of (await result.json()).memories) {
      if (memory.content.includes(marker)) await page.request.delete(`${baseUrl}/api/v1/memories/${memory.memory_id}`, { headers });
    }
  }
  await browser.close();
}
