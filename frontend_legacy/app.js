const tenantIdInput = document.getElementById("tenantId");
const userIdInput = document.getElementById("userId");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");

let accessToken = "";
let selectedConversationId = "";
let selectedTicketId = "";
let selectedApprovalId = "";

function escapeHtml(value) {
  return String(value ?? "")
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

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body?.error?.message || `HTTP ${response.status}`);
  }
  return response.json();
}

function api(method, path, body) {
  const options = {
    method,
    headers: authHeaders(Boolean(body)),
  };
  if (body !== undefined) options.body = JSON.stringify(body);
  return requestJson(path, options);
}

function showView(name) {
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.view === name));
  const target = document.getElementById(`view-${name}`);
  if (target) target.classList.add("active");
  if (name === "overview") refreshOverview();
  if (name === "conversations") refreshConversations();
  if (name === "tickets") refreshTickets();
  if (name === "approvals") refreshApprovals();
  if (name === "knowledge") refreshKnowledgeDocuments();
  if (name === "evaluations") refreshEvaluations();
}

function statusClass(value) {
  const normalized = String(value || "").toLowerCase();
  if (["resolved", "closed", "completed", "succeeded", "allow"].includes(normalized)) return "success";
  if (["pending", "pending_approval", "pending_customer", "in_progress", "running"].includes(normalized)) return "warning";
  if (["failed", "blocked", "cancelled", "rejected", "error", "unknown"].includes(normalized)) return "danger";
  return "";
}

function statusBadge(value) {
  return `<span class="status ${statusClass(value)}">${escapeHtml(value)}</span>`;
}

function renderRows(container, items, renderItem, emptyText) {
  if (!items.length) {
    container.className = "list empty";
    container.textContent = emptyText || "暂无数据";
    return;
  }
  container.className = "list";
  container.innerHTML = items.map(renderItem).join("");
}

document.getElementById("tokenBtn").addEventListener("click", async () => {
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
    setStatus("Token 已获取", true);
  } catch (error) {
    setStatus(`Token 失败：${error.message}`, false);
  }
});

function appendEvent(container, name, data) {
  if (container.classList.contains("empty")) {
    container.textContent = "";
    container.classList.remove("empty");
  }
  const row = document.createElement("div");
  row.className = "event-row";
  const label = document.createElement("div");
  label.className = "event-name";
  label.textContent = name;
  const value = document.createElement("div");
  value.textContent = JSON.stringify(data);
  row.append(label, value);
  container.append(row);
  container.scrollTop = container.scrollHeight;
}

function handleSseBlock(container, block) {
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
    appendEvent(container, eventName, data);
  } catch {
    appendEvent(container, eventName, dataLines.join("\n"));
  }
}

document.getElementById("consultationSendBtn").addEventListener("click", async () => {
  const message = document.getElementById("consultationMessage").value.trim();
  const events = document.getElementById("consultationEvents");
  if (!message) return;
  events.textContent = "";
  events.classList.add("empty");
  events.textContent = "连接中...";
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
    events.classList.remove("empty");
    events.textContent = "";
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";
      blocks.forEach((block) => handleSseBlock(events, block));
    }
    setStatus("SSE 完成", true);
  } catch (error) {
    events.classList.remove("empty");
    appendEvent(events, "error", { message: error.message });
    setStatus("SSE 失败", false);
  }
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => showView(tab.dataset.view));
});

async function refreshOverview() {
  try {
    const health = await api("GET", "/healthz");
    const tickets = await api("GET", "/api/v1/tickets?limit=5");
    const approvals = await api("GET", "/api/v1/approvals?limit=20");
    const docs = await api("GET", "/api/v1/knowledge/documents?limit=20");
    document.getElementById("overviewHealth").textContent = health.status || "ok";
    document.getElementById("overviewTickets").textContent = tickets.tickets.length;
    document.getElementById("overviewApprovals").textContent = approvals.approvals.filter((item) => item.status === "pending").length;
    document.getElementById("overviewDocs").textContent = docs.documents.length;
    const events = [
      { name: "healthz", data: health },
      { name: "tickets", data: { count: tickets.tickets.length } },
      { name: "approvals", data: { pending: approvals.approvals.filter((item) => item.status === "pending").length } },
    ];
    renderOverviewEvents(events);
    setStatus("总览已刷新", true);
  } catch (error) {
    setStatus(`总览失败：${error.message}`, false);
  }
}

function renderOverviewEvents(events) {
  const container = document.getElementById("overviewEvents");
  if (!events.length) {
    container.className = "empty-state";
    container.textContent = "暂无事件";
    return;
  }
  container.className = "empty-state";
  container.innerHTML = events
    .map(
      (event) => `
        <div class="event-row">
          <div class="event-name">${escapeHtml(event.name)}</div>
          <div>${escapeHtml(JSON.stringify(event.data))}</div>
        </div>
      `,
    )
    .join("");
}

document.getElementById("overviewRefreshBtn").addEventListener("click", refreshOverview);

async function refreshConversations() {
  const container = document.getElementById("conversationList");
  try {
    const body = await api("GET", "/api/v1/conversations");
    renderRows(
      container,
      body.conversations || [],
      (item) => `
        <div class="row" data-id="${escapeHtml(item.conversation_id)}">
          <div class="row-title">${escapeHtml(item.subject)}</div>
          <div class="row-meta">${escapeHtml(item.channel)} · ${escapeHtml(item.status)} · ${item.message_count} 条消息</div>
        </div>
      `,
      "暂无会话",
    );
  } catch (error) {
    container.className = "list empty";
    container.textContent = `读取失败：${escapeHtml(error.message)}`;
  }
}

document.getElementById("createConversationBtn").addEventListener("click", async () => {
  try {
    await api("POST", "/api/v1/conversations", {
      customer_id: document.getElementById("convCustomerId").value.trim() || null,
      user_id: document.getElementById("convUserId").value.trim() || null,
      channel: document.getElementById("convChannel").value,
      subject: document.getElementById("convSubject").value.trim(),
      initial_message: document.getElementById("convInitialMessage").value.trim() || null,
    });
    setStatus("会话已创建", true);
    await refreshConversations();
  } catch (error) {
    setStatus(`会话创建失败：${error.message}`, false);
  }
});

document.getElementById("refreshConversationsBtn").addEventListener("click", refreshConversations);

document.getElementById("conversationList").addEventListener("click", async (event) => {
  const row = event.target.closest("[data-id]");
  if (!row) return;
  selectedConversationId = row.dataset.id;
  try {
    const body = await api("GET", `/api/v1/conversations/${selectedConversationId}`);
    renderConversationDetail(body);
  } catch (error) {
    document.getElementById("conversationDetail").textContent = `读取失败：${escapeHtml(error.message)}`;
  }
});

function renderConversationDetail(body) {
  const conversation = body.conversation;
  const messages = body.messages || [];
  document.getElementById("conversationDetail").innerHTML = `
    <div class="detail-block">
      <div class="detail-label">状态</div>
      <div class="detail-value">${statusBadge(conversation.status)}</div>
    </div>
    <div class="detail-block">
      <div class="detail-label">渠道</div>
      <div class="detail-value">${escapeHtml(conversation.channel)}</div>
    </div>
    <div class="detail-block">
      <div class="detail-label">消息</div>
      <div class="detail-value">${messages.map((item) => `${escapeHtml(item.role)}: ${escapeHtml(item.body)}`).join("<br />") || "暂无消息"}</div>
    </div>
  `;
}

document.getElementById("sendConversationMessageBtn").addEventListener("click", async () => {
  const body = document.getElementById("conversationMessageBody").value.trim();
  if (!selectedConversationId || !body) return;
  try {
    const detail = await api("POST", `/api/v1/conversations/${selectedConversationId}/messages`, {
      role: "user",
      body,
      visibility: "public",
    });
    document.getElementById("conversationMessageBody").value = "";
    renderConversationDetail(detail);
    await refreshConversations();
  } catch (error) {
    setStatus(`消息发送失败：${error.message}`, false);
  }
});

async function refreshTickets() {
  const container = document.getElementById("ticketList");
  try {
    const body = await api("GET", "/api/v1/tickets");
    renderRows(
      container,
      body.tickets || [],
      (item) => `
        <div class="row" data-id="${escapeHtml(item.ticket_id)}">
          <div class="row-title">${escapeHtml(item.subject)}</div>
          <div class="row-meta">${statusBadge(item.status)} · ${escapeHtml(item.priority)} · ${new Date(item.updated_at).toLocaleString()}</div>
        </div>
      `,
      "暂无工单",
    );
  } catch (error) {
    container.className = "list empty";
    container.textContent = `读取失败：${escapeHtml(error.message)}`;
  }
}

document.getElementById("createTicketBtn").addEventListener("click", async () => {
  try {
    await api("POST", "/api/v1/tickets", {
      thread_id: `console-ticket-${Date.now()}`,
      customer_id: document.getElementById("ticketCustomerId").value.trim(),
      subject: document.getElementById("ticketSubject").value.trim(),
      priority: document.getElementById("ticketPriority").value,
      description_summary: document.getElementById("ticketDescription").value.trim() || null,
      message: document.getElementById("ticketMessage").value.trim() || null,
    });
    setStatus("工单已创建", true);
    await refreshTickets();
  } catch (error) {
    setStatus(`工单创建失败：${error.message}`, false);
  }
});

document.getElementById("refreshTicketsBtn").addEventListener("click", refreshTickets);

document.getElementById("ticketList").addEventListener("click", async (event) => {
  const row = event.target.closest("[data-id]");
  if (!row) return;
  selectedTicketId = row.dataset.id;
  try {
    const body = await api("GET", `/api/v1/tickets/${selectedTicketId}`);
    renderTicketDetail(body);
  } catch (error) {
    document.getElementById("ticketDetail").textContent = `读取失败：${escapeHtml(error.message)}`;
  }
});

function renderTicketDetail(body) {
  const ticket = body.ticket;
  document.getElementById("ticketDetail").innerHTML = `
    <div class="detail-block">
      <div class="detail-label">状态</div>
      <div class="detail-value">${statusBadge(ticket.status)}</div>
    </div>
    <div class="detail-block">
      <div class="detail-label">主题</div>
      <div class="detail-value">${escapeHtml(ticket.subject)}</div>
    </div>
    <div class="detail-block">
      <div class="detail-label">事件</div>
      <div class="detail-value">${(body.events || []).map((item) => `${escapeHtml(item.event_type)} → ${escapeHtml(item.to_status || "-")}`).join("<br />") || "暂无事件"}</div>
    </div>
    <div class="detail-block">
      <div class="detail-label">消息</div>
      <div class="detail-value">${(body.messages || []).map((item) => escapeHtml(item.body)).join("<br />") || "暂无消息"}</div>
    </div>
  `;
}

document.getElementById("updateTicketBtn").addEventListener("click", async () => {
  if (!selectedTicketId) return;
  try {
    const body = await api("PATCH", `/api/v1/tickets/${selectedTicketId}`, {
      status: document.getElementById("ticketStatusSelect").value,
      note: document.getElementById("ticketPatchNote").value.trim() || null,
    });
    document.getElementById("ticketPatchNote").value = "";
    renderTicketDetail(body);
    await refreshTickets();
    setStatus("工单已更新", true);
  } catch (error) {
    setStatus(`工单更新失败：${error.message}`, false);
  }
});

async function refreshApprovals() {
  const container = document.getElementById("approvalList");
  try {
    const body = await api("GET", "/api/v1/approvals");
    renderRows(
      container,
      body.approvals || [],
      (item) => `
        <div class="row" data-id="${escapeHtml(item.approval_request_id)}">
          <div class="row-title">${escapeHtml(item.action)} · ${escapeHtml(item.approval_role)}</div>
          <div class="row-meta">${statusBadge(item.status)} · ${escapeHtml(item.amount || "-")} · ${escapeHtml(item.risk_level)}</div>
        </div>
      `,
      "暂无审批",
    );
  } catch (error) {
    container.className = "list empty";
    container.textContent = `读取失败：${escapeHtml(error.message)}`;
  }
}

document.getElementById("refreshApprovalsBtn").addEventListener("click", refreshApprovals);

document.getElementById("approvalList").addEventListener("click", async (event) => {
  const row = event.target.closest("[data-id]");
  if (!row) return;
  selectedApprovalId = row.dataset.id;
  try {
    const body = await api("GET", `/api/v1/approvals/${selectedApprovalId}`);
    const approval = body.approval;
    document.getElementById("approvalDetail").innerHTML = `
      <div class="detail-block">
        <div class="detail-label">状态</div>
        <div class="detail-value">${statusBadge(approval.status)}</div>
      </div>
      <div class="detail-block">
        <div class="detail-label">金额</div>
        <div class="detail-value">${escapeHtml(approval.amount || "-")}</div>
      </div>
      <div class="detail-block">
        <div class="detail-label">风险</div>
        <div class="detail-value">${escapeHtml(approval.risk_level)}</div>
      </div>
      <div class="detail-block">
        <div class="detail-label">动作</div>
        <div class="detail-value">${(body.actions || []).map((item) => `${escapeHtml(item.action)}: ${escapeHtml(item.reason)}`).join("<br />") || "暂无动作"}</div>
      </div>
    `;
    document.getElementById("approvalThreadId").value = approval.checkpoint_reference || "";
  } catch (error) {
    document.getElementById("approvalDetail").textContent = `读取失败：${escapeHtml(error.message)}`;
  }
});

document.getElementById("approvalActionBtn").addEventListener("click", async () => {
  if (!selectedApprovalId) return;
  try {
    await api("POST", `/api/v1/approvals/${selectedApprovalId}`, {
      thread_id: document.getElementById("approvalThreadId").value.trim(),
      approved: document.getElementById("approvalDecision").value === "true",
      reason: document.getElementById("approvalReason").value.trim(),
    });
    setStatus("审批决策已提交", true);
    await refreshApprovals();
  } catch (error) {
    setStatus(`审批提交失败：${error.message}`, false);
  }
});

document.getElementById("knowledgeSearchBtn").addEventListener("click", async () => {
  const query = document.getElementById("knowledgeQuery").value.trim();
  const container = document.getElementById("knowledgeResults");
  if (!query) return;
  try {
    const params = new URLSearchParams({ q: query, limit: "5" });
    const body = await api("GET", `/api/v1/knowledge/search?${params}`);
    renderRows(
      container,
      body.results || [],
      (item) => `
        <div class="knowledge-item">
          <div class="knowledge-title">${escapeHtml(item.title)}</div>
          <div class="knowledge-meta">${escapeHtml(item.external_document_id)}${item.score != null ? ` · ${Number(item.score).toFixed(4)}` : ""}</div>
          ${item.content_snippet ? `<div class="knowledge-meta">${escapeHtml(item.content_snippet)}</div>` : ""}
        </div>
      `,
      "暂无结果",
    );
  } catch (error) {
    container.className = "list empty";
    container.textContent = `检索失败：${escapeHtml(error.message)}`;
  }
});

async function refreshKnowledgeDocuments() {
  const container = document.getElementById("knowledgeDocList");
  try {
    const body = await api("GET", "/api/v1/knowledge/documents");
    renderRows(
      container,
      body.documents || [],
      (item) => `
        <div class="row" data-id="${escapeHtml(item.document_id)}">
          <div class="row-title">${escapeHtml(item.title)}</div>
          <div class="row-meta">${statusBadge(item.status)} · ${escapeHtml(item.visibility)}</div>
          <div class="actions" style="margin-top:6px">
            <button class="doc-delete" type="button">删除</button>
          </div>
        </div>
      `,
      "暂无文档",
    );
  } catch (error) {
    container.className = "list empty";
    container.textContent = `读取失败：${escapeHtml(error.message)}`;
  }
}

document.getElementById("refreshDocsBtn").addEventListener("click", refreshKnowledgeDocuments);

document.getElementById("knowledgeDocList").addEventListener("click", async (event) => {
  const row = event.target.closest("[data-id]");
  const deleteButton = event.target.closest(".doc-delete");
  if (!row || !deleteButton) return;
  try {
    await api("DELETE", `/api/v1/knowledge/documents/${row.dataset.id}`);
    setStatus("文档已归档", true);
    await refreshKnowledgeDocuments();
  } catch (error) {
    setStatus(`文档删除失败：${error.message}`, false);
  }
});

document.getElementById("ingestKnowledgeBtn").addEventListener("click", async () => {
  try {
    await api("POST", "/api/v1/knowledge/documents", {
      thread_id: `console-knowledge-${Date.now()}`,
      external_document_id: document.getElementById("docExternalId").value.trim(),
      title: document.getElementById("docTitle").value.trim(),
      source_uri: document.getElementById("docSourceUri").value.trim() || null,
      visibility: document.getElementById("docVisibility").value,
      content: document.getElementById("docContent").value,
    });
    setStatus("文档已摄取", true);
    await refreshKnowledgeDocuments();
  } catch (error) {
    setStatus(`文档摄取失败：${error.message}`, false);
  }
});

document.getElementById("reindexKnowledgeBtn").addEventListener("click", async () => {
  try {
    const body = await api("POST", "/api/v1/knowledge/reindex");
    setStatus(`重建索引完成：${body.document_count} 文档 / ${body.chunk_count} 分片`, true);
  } catch (error) {
    setStatus(`重建索引失败：${error.message}`, false);
  }
});

async function fetchRuntime(path) {
  return api("GET", `/api/v1/runtime${path}`);
}

function renderRuntime(data) {
  const output = document.getElementById("runtimeOutput");
  output.classList.remove("empty");
  output.textContent = JSON.stringify(data, null, 2);
}

document.getElementById("tracesBtn").addEventListener("click", async () => {
  try {
    renderRuntime(await fetchRuntime("/traces"));
  } catch (error) {
    document.getElementById("runtimeOutput").textContent = `读取失败：${error.message}`;
  }
});

document.getElementById("costsBtn").addEventListener("click", async () => {
  try {
    renderRuntime(await fetchRuntime("/costs"));
  } catch (error) {
    document.getElementById("runtimeOutput").textContent = `读取失败：${error.message}`;
  }
});

document.getElementById("agentsBtn").addEventListener("click", async () => {
  try {
    renderRuntime(await fetchRuntime("/agents"));
  } catch (error) {
    document.getElementById("runtimeOutput").textContent = `读取失败：${error.message}`;
  }
});

async function refreshEvaluations() {
  const container = document.getElementById("evaluationList");
  try {
    const body = await api("GET", "/api/v1/evaluations");
    renderRows(
      container,
      body.runs || [],
      (item) => `
        <div class="row">
          <div class="row-title">${escapeHtml(item.dataset_id)}</div>
          <div class="row-meta">${statusBadge(item.status)} · ${escapeHtml(JSON.stringify(item.metrics))}</div>
        </div>
      `,
      "暂无评测",
    );
  } catch (error) {
    container.className = "list empty";
    container.textContent = `读取失败：${escapeHtml(error.message)}`;
  }
}

document.getElementById("refreshEvalsBtn").addEventListener("click", refreshEvaluations);

document.getElementById("runEvalBtn").addEventListener("click", async () => {
  try {
    await api("POST", "/api/v1/evaluations/run", {
      dataset_code: document.getElementById("evalDatasetCode").value.trim(),
      limit: Number(document.getElementById("evalLimit").value || 5),
    });
    setStatus("评测已完成", true);
    await refreshEvaluations();
  } catch (error) {
    setStatus(`评测失败：${error.message}`, false);
  }
});

showView("overview");
