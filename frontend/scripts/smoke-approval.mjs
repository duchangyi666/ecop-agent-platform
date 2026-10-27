/** Exercise the local demo's approval UI and its authorization boundaries. */
import { randomUUID } from "node:crypto";
import { chromium } from "playwright";

const baseUrl = process.env.SMOKE_BASE_URL ?? "http://127.0.0.1:3000";
const tenantSlug = process.env.SMOKE_TENANT_SLUG ?? "clouddesk-demo";
const paymentId = process.env.SMOKE_PAYMENT_ID;
const host = new URL(baseUrl).hostname;
if (!["localhost", "127.0.0.1", "[::1]"].includes(host) || !paymentId) {
  throw new Error("Use a local demo URL and set SMOKE_PAYMENT_ID from seed_demo_scenario.py");
}
const escaped = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const browser = await chromium.launch();
const page = await browser.newPage();
page.setDefaultTimeout(20000);

async function selectIdentity(email) {
  await page.goto(`${baseUrl}/identity`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: new RegExp(`^${escaped(tenantSlug)} `) }).click();
  await page.getByRole("button", { name: new RegExp(escaped(email)) }).click();
  await page.waitForURL("**/chat");
  const identity = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("clouddesk-identity")).state.identity,
  );
  return { "X-Tenant-Id": identity.tenantId, "X-Actor-Id": identity.userId,
    "X-Actor-Type": identity.actorType };
}

async function expectStatus(response, status, action) {
  if (response.status() !== status) {
    throw new Error(`${action}: expected HTTP ${status}, got ${response.status()}: ${await response.text()}`);
  }
}

try {
  const admin = await selectIdentity("admin@clouddesk.demo");
  const thread = `browser-refund-${randomUUID()}`;
  const payload = { thread_id: thread, payment_id: paymentId, amount: "1280.00",
    refund_idempotency_key: `browser-${randomUUID()}`, message: "申请退款" };
  const guest = await selectIdentity("guest@clouddesk.demo");
  await expectStatus(await page.request.post(`${baseUrl}/api/v1/refunds`, {
    headers: guest, data: payload,
  }), 403, "guest refund");

  const created = await page.request.post(`${baseUrl}/api/v1/refunds`, { headers: admin, data: payload });
  await expectStatus(created, 202, "create refund");
  const refund = await created.json();
  if (refund.status !== "awaiting_approval" || !refund.approval_request_id || !refund.trace_id) {
    throw new Error("refund did not produce a pending approval and trace");
  }
  const approvalUrl = `${baseUrl}/api/v1/approvals/${refund.approval_request_id}`;
  const decision = { thread_id: thread, approved: true, reason: "浏览器演示审批" };
  await expectStatus(await page.request.post(approvalUrl, { headers: guest, data: decision }), 403,
    "guest approval");

  const finance = await selectIdentity("finance@clouddesk.demo");
  await page.getByRole("link", { name: "客服工作台", exact: true }).click();
  await page.locator(`a[href="/workspace/approvals/${refund.approval_request_id}"]`).click();
  await page.waitForURL(`**/workspace/approvals/${refund.approval_request_id}`);
  await page.getByText("待审批", { exact: true }).waitFor();
  await page.getByPlaceholder("审批备注（可选）").fill(decision.reason);
  await page.getByRole("button", { name: "批准", exact: true }).click();
  await page.getByText("确认批准该请求？", { exact: true }).waitFor();
  await page.getByRole("button", { name: "确认", exact: true }).click();
  await page.getByText("已批准", { exact: true }).waitFor();
  await page.getByText(decision.reason, { exact: true }).waitFor();
  if (await page.getByRole("button", { name: "批准", exact: true }).count()) {
    throw new Error("approved request still offers the approval action");
  }
  await expectStatus(await page.request.post(approvalUrl, { headers: finance, data: decision }), 409,
    "duplicate approval");
  const detail = await page.request.get(approvalUrl, { headers: finance });
  await expectStatus(detail, 200, "read approval");
  const approval = await detail.json();
  if (approval.approval.status !== "approved" || approval.actions.length !== 1) {
    throw new Error("duplicate approval changed the persisted action count or status");
  }
  await page.goto(`${baseUrl}/admin/runtime/${refund.trace_id}`);
  await page.getByText("approved_for_execution", { exact: true }).waitFor();
  await page.getByText("agent.refund", { exact: true }).waitFor();
  console.log("PASS: guest denied, finance approval recorded once, runtime trace visible");
} catch (error) {
  console.error("FAIL: approval smoke:", error instanceof Error ? error.message : error);
  process.exitCode = 1;
} finally {
  await browser.close();
}
