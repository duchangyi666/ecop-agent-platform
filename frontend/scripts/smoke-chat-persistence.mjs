/** Browser regression for chat persistence with the seeded local demo. */
import { chromium } from "playwright";

const baseUrl = process.env.SMOKE_BASE_URL ?? "http://127.0.0.1:3000";
const tenantSlug = process.env.SMOKE_TENANT_SLUG ?? "clouddesk-demo";
const question = "企业版 SLA 与支持等级";
const escapedTenant = tenantSlug.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const browser = await chromium.launch();
const page = await browser.newPage();
page.setDefaultTimeout(20000);

async function selectIdentity(email) {
  await page.goto(`${baseUrl}/identity`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: new RegExp(`^${escapedTenant} `) }).click();
  await page.getByRole("button", { name: new RegExp(email.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) }).click();
  await page.waitForURL("**/chat");
}

try {
  await selectIdentity("customer@clouddesk.demo");
  const input = page.getByRole("textbox", { name: "描述您的问题，支持连续对话…" });
  await input.fill(question);
  await page.getByRole("button", { name: "发送" }).click();
  await page.getByText("2 条消息 · 多轮对话中", { exact: true }).waitFor();

  await page.getByRole("link", { name: "我的工单" }).click();
  await page.getByText("演示工单：账单金额与扣费疑问", { exact: true }).waitFor();
  await page.getByRole("link", { name: "对话", exact: true }).click();
  await page.getByText(question, { exact: true }).waitFor();
  await page.getByText("2 条消息 · 多轮对话中", { exact: true }).waitFor();

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByText(question, { exact: true }).waitFor();
  await page.getByText("2 条消息 · 多轮对话中", { exact: true }).waitFor();

  await selectIdentity("agent@clouddesk.demo");
  await page.getByRole("heading", { name: "CloudDesk 智能客服" }).waitFor();
  if (await page.getByText(question, { exact: true }).count()) {
    throw new Error("customer conversation is visible under a different identity");
  }

  await selectIdentity("customer@clouddesk.demo");
  await page.getByText(question, { exact: true }).waitFor();
  await page.getByText("2 条消息 · 多轮对话中", { exact: true }).waitFor();
  console.log("PASS: chat survives navigation and reload, and stays scoped to its identity");
} catch (error) {
  console.error("FAIL: chat persistence smoke:", error instanceof Error ? error.message : error);
  process.exitCode = 1;
} finally {
  await browser.close();
}
