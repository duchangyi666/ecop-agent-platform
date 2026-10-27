/** Verify that an SPA identity switch cannot reuse the previous user's data. */
import { chromium } from "playwright";

const baseUrl = process.env.SMOKE_BASE_URL ?? "http://127.0.0.1:3000";
const tenantSlug = process.env.SMOKE_TENANT_SLUG ?? "clouddesk-demo";
const tenantPattern = tenantSlug.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const ticketTitle = "演示工单：账单金额与扣费疑问";
const browser = await chromium.launch();
const page = await browser.newPage();
page.setDefaultTimeout(20000);

async function selectFromPicker(email) {
  await page.getByRole("button", { name: new RegExp(`^${tenantPattern} `) }).click();
  await page.getByRole("button", {
    name: new RegExp(email.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
  }).click();
  await page.waitForURL("**/chat");
}

try {
  await page.goto(`${baseUrl}/identity`, { waitUntil: "domcontentloaded" });
  await selectFromPicker("customer@clouddesk.demo");
  await page.getByRole("link", { name: "我的工单" }).click();
  await page.getByText(ticketTitle, { exact: true }).waitFor();

  // Use client-side navigation so the React Query cache survives the switch.
  await page.getByRole("link", { name: new RegExp(`演示客户 ${tenantPattern}`) }).click();
  await selectFromPicker("guest@clouddesk.demo");
  const denied = page.waitForResponse((response) =>
    response.url().includes("/api/v1/conversations") && response.status() === 403,
  );
  await page.getByRole("link", { name: "客户门户", exact: true }).click();
  await denied;
  await page.getByRole("heading", { name: "客户门户", exact: true }).waitFor();
  if (await page.getByText(ticketTitle, { exact: true }).count()) {
    throw new Error("guest can see the previous customer's cached ticket");
  }
  await page.getByText("权限不足", { exact: true }).first().waitFor();

  // A dev identity selection must also discard any previously stored bearer.
  await page.goto(`${baseUrl}/identity`, { waitUntil: "domcontentloaded" });
  await selectFromPicker("customer@clouddesk.demo");
  const identity = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("clouddesk-identity")).state.identity,
  );
  const tokenResponse = await page.request.post(`${baseUrl}/api/v1/auth/tokens`, {
    data: { tenant_id: identity.tenantId, user_id: identity.userId },
  });
  if (!tokenResponse.ok()) throw new Error("could not obtain local demo token");
  const token = (await tokenResponse.json()).access_token;
  await page.evaluate((accessToken) => {
    const stored = JSON.parse(localStorage.getItem("clouddesk-identity"));
    stored.state.accessToken = accessToken;
    localStorage.setItem("clouddesk-identity", JSON.stringify(stored));
  }, token);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("link", { name: "我的工单" }).click();
  await page.getByText(ticketTitle, { exact: true }).waitFor();
  await page.getByRole("link", { name: new RegExp(`演示客户 ${tenantPattern}`) }).click();
  await selectFromPicker("guest@clouddesk.demo");
  const tokenDenied = page.waitForResponse((response) =>
    response.url().includes("/api/v1/conversations") && response.status() === 403,
  );
  await page.getByRole("link", { name: "客户门户", exact: true }).click();
  await tokenDenied;
  await page.getByText("权限不足", { exact: true }).first().waitFor();
  if (await page.getByText(ticketTitle, { exact: true }).count()) {
    throw new Error("guest can see data from a previous bearer session");
  }

  console.log("PASS: identity switch clears cached data and any previous bearer token");
} catch (error) {
  console.error("FAIL: identity cache smoke:", error instanceof Error ? error.message : error);
  process.exitCode = 1;
} finally {
  await browser.close();
}
