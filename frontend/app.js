const tenantIdInput = document.getElementById("tenantId");
const userIdInput = document.getElementById("userId");
const tokenOutput = document.getElementById("tokenOutput");
const knowledgeQuery = document.getElementById("knowledgeQuery");
const knowledgeResults = document.getElementById("knowledgeResults");
const messageInput = document.getElementById("message");
const eventsOutput = document.getElementById("events");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");

let accessToken = "";

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setStatus(text, ready = false) {
  statusText.textContent = text;
  statusDot.classList.toggle("ready", ready);
}

function authHeaders(json = true) {
  const headers = {};
  if (json) headers["Content-Type"] = "application/json";
  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  } else {
    headers["X-Tenant-Id"] = tenantIdInput.value.trim();
    headers["X-Actor-Id"] = userIdInput.value.trim();
    headers["X-Actor-Type"] = "user";
  }
  return headers;
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body?.error?.message || `HTTP ${response.status}`);
  }
  return response.json();
}

document.getElementById("tokenBtn").addEventListener("click", async () => {
  tokenOutput.textContent = "获取中...";
  tokenOutput.classList.remove("empty");
  try {
    const body = await requestJson("/api/v1/auth/tokens", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tenant_id: tenantIdInput.value.trim(),
        user_id: userIdInput.value.trim(),
        actor_type: "user",
      }),
    });
    accessToken = body.access_token;
    tokenOutput.textContent = `token_type: ${body.token_type}\nexpires_in: ${body.expires_in}\naccess_token: ${body.access_token}`;
    setStatus("Token 已获取", true);
  } catch (error) {
    tokenOutput.textContent = `错误：${escapeHtml(error.message)}`;
    setStatus("Token 获取失败", false);
  }
});

document.getElementById("knowledgeBtn").addEventListener("click", async () => {
  const query = knowledgeQuery.value.trim();
  if (!query) return;
  knowledgeResults.textContent = "检索中...";
  knowledgeResults.classList.remove("empty");
  try {
    const params = new URLSearchParams({ q: query, limit: "5" });
    const body = await requestJson(`/api/v1/knowledge/search?${params}`, {
      method: "GET",
      headers: authHeaders(false),
    });
    renderKnowledgeResults(body.results || []);
    setStatus("知识检索完成", true);
  } catch (error) {
    knowledgeResults.textContent = `错误：${escapeHtml(error.message)}`;
    setStatus("知识检索失败", false);
  }
});

function renderKnowledgeResults(results) {
  if (!results.length) {
    knowledgeResults.textContent = "暂无结果";
    knowledgeResults.classList.add("empty");
    return;
  }
  knowledgeResults.classList.remove("empty");
  knowledgeResults.innerHTML = results
    .map(
      (item) => `
        <div class="knowledge-item">
          <div class="knowledge-title">${escapeHtml(item.title)}</div>
          <div class="knowledge-meta">${escapeHtml(item.external_document_id)}${item.score != null ? ` · score ${Number(item.score).toFixed(4)}` : ""}</div>
          ${item.content_snippet ? `<div class="knowledge-meta">${escapeHtml(item.content_snippet)}</div>` : ""}
        </div>
      `,
    )
    .join("");
}

function appendEvent(name, data) {
  if (eventsOutput.classList.contains("empty")) {
    eventsOutput.textContent = "";
    eventsOutput.classList.remove("empty");
  }
  const row = document.createElement("div");
  row.className = "event-row";
  const label = document.createElement("div");
  label.className = "event-name";
  label.textContent = name;
  const value = document.createElement("div");
  value.textContent = JSON.stringify(data);
  row.append(label, value);
  eventsOutput.append(row);
  eventsOutput.scrollTop = eventsOutput.scrollHeight;
}

function handleSseBlock(block) {
  const lines = block.split("\n");
  let eventName = "";
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!eventName || !dataLines.length) return;
  try {
    const data = JSON.parse(dataLines.join("\n"));
    appendEvent(eventName, data);
  } catch {
    appendEvent(eventName, dataLines.join("\n"));
  }
}

document.getElementById("askBtn").addEventListener("click", async () => {
  const message = messageInput.value.trim();
  if (!message) return;
  eventsOutput.textContent = "";
  eventsOutput.classList.add("empty");
  eventsOutput.textContent = "连接中...";
  try {
    const response = await fetch("/api/v1/customer-consultations/stream", {
      method: "POST",
      headers: authHeaders(true),
      body: JSON.stringify({
        thread_id: `console-${Date.now()}`,
        message,
      }),
    });
    if (!response.ok || !response.body) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body?.error?.message || `HTTP ${response.status}`);
    }
    eventsOutput.classList.remove("empty");
    eventsOutput.textContent = "";
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";
      blocks.forEach(handleSseBlock);
    }
    setStatus("SSE 完成", true);
  } catch (error) {
    eventsOutput.classList.remove("empty");
    appendEvent("error", { message: error.message });
    setStatus("SSE 失败", false);
  }
});
