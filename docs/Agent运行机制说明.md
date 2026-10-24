# CloudDesk Agent 运行机制说明

> 适用代码基线：`main @ 9368e8a`；核对时间：2026-10-21。
> 当前本机运行态：PostgreSQL `54330`、Milvus `19541`、后端 `8080`、前端 `3000`；已配置 `DEEPSEEK_API_KEY`，模型走真实 DeepSeek（`provider=deepseek`），未配置时自动回退离线 `FakeModelGateway`。

本文回答四个问题：Agent 怎么跑起来、上下文怎么管理、工具怎么调用、当前有哪些工具。文末给出当前实现边界与本地启动/验证方式。

---

## 1. 一页结论

1. **不是 AutoGPT 式的自由工具调用**。系统是 **LangGraph 固定图编排 + 结构化意图决策 + 确定性工具执行**：模型只负责“判断该做什么/怎么写回复”，真正写数据库、建工单、发退款申请由后端代码在租户事务内完成。
2. **主图只有一个“生成回复”的节点**（客服节点），其余节点负责守门、检索、路由、执行业务动作；客服节点内部再区分“结构化模式”和“流式模式”。
3. **上下文 = 客户端传入的 `history` + 当前消息 + RAG 证据 + 业务动作结果**。服务端会把每轮对话落库，但**不会按 `thread_id` 自动回灌历史**；多轮上下文目前依赖前端把历史一并传回。
4. **工具 = 4 个业务 Tool 类 + 6 种会话动作 + 2 个可选 MCP 工具**。所有业务工具都在 `TenantScope` + `UnitOfWork` 内执行，并写审计日志与 Runtime Trace。
5. **退款不是自动打款**。高风险退款只创建本地退款申请 + 审批 Checkpoint，必须人工审批后才进入“可执行”状态；真实资金到账不在本仓库范围内。

---

## 2. 运行拓扑与当前状态

| 组件 | 地址/端口 | 当前状态 | 说明 |
| --- | --- | --- | --- |
| Next.js 前端 | `http://127.0.0.1:3000` | ✅ 运行中 | `next dev`，`BACKEND_URL=http://localhost:8080` |
| FastAPI 后端 | `http://127.0.0.1:8080` | ✅ 运行中 | `/docs`、`/healthz`、`/metrics` 可用 |
| PostgreSQL | `localhost:54330` | ✅ 41 张表，Alembic `009 (head)` | `verify_database.py` 通过 |
| Milvus | `http://localhost:19541` | ✅ 端口可连通 | 知识向量检索使用；无集合时回退 PG |
| Redis | `localhost:16380` | ❌ 未启动 | 仅 Worker/Scheduler 需要，聊天链路不依赖 |
| MCP 服务 | `/mcp/kb`、`/mcp/web-search` | ❌ 未挂载 | 未安装可选依赖 `mcp`，启动日志会提示 `mcp mount skipped` |
| 本地 BGE-M3 / Reranker | `models/bge-m3` | ❌ 不存在 | 当前使用确定性离线 Embedding + 确定性排序 |
| DeepSeek | `api.deepseek.com` | ✅ 已配置 Key | 真实调用 `deepseek-v4-flash`；未配置 Key 时回退 `FakeModelGateway` |

前端通过 `next.config.ts` 的 rewrite 把 `/api/*` 代理到 `BACKEND_URL`；后端同时把旧版控制台 `frontend_legacy/` 挂在 `/`。

### 启动命令（当前本机）

推荐用脚本启动（会先加载根目录 `.env`，再启动 uvicorn）：

```powershell
.\scripts\run_demo_backend.ps1
```

等价的手工方式：

```powershell
$env:PYTHONNOUSERSITE = "1"
$env:DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54330/enterprise_customer_operations"
$env:MILVUS_URI = "http://localhost:19541"
$env:JWT_SECRET = "<32 字节以上随机串>"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8080
```

```powershell
cd frontend
$env:BACKEND_URL = "http://localhost:8080"
npm run build
npm run start
```

> 对外演示请用生产构建（`npm run build` + `npm run start`）；`next dev` 会显示 Next.js 开发指示器，且首屏更慢。开发调试时才用 `npm run dev`。

> 后端本身不自动读取根目录 `.env`；`scripts/run_demo_backend.ps1` 会逐行加载 `.env` 后再启动。把 `DEEPSEEK_API_KEY` 填进 `.env` 后重启脚本即可切换真实模型。`.env` 已被 `.gitignore` 忽略。
> `.env` 中的 `BGE_M3_MODEL_PATH` 必须留空（或指向真实存在的模型目录），否则启动时会因 `BGE-M3 model path does not exist` 失败；当前没有 `models/bge-m3`，所以保持为空、使用离线 Embedding。
> Next.js 的 `next dev`/`next build` 在当前 DSH 沙箱内会因 `spawn EPERM` 失败，需要放宽沙箱权限（或把前端放到普通终端启动）。

---

## 3. 一次咨询请求的完整生命周期

入口有两个：

- `POST /api/v1/customer-consultations`：普通 JSON 响应；
- `POST /api/v1/customer-consultations/stream`：SSE 流式响应。

两者都走同一个 `CustomerConsultationService`，区别只在事件输出方式。

```mermaid
sequenceDiagram
    participant UI as 前端
    participant API as FastAPI 路由
    participant SVC as ConsultationService
    participant G as LangGraph 主图
    participant DB as PostgreSQL
    participant M as ModelGateway
    participant ML as Milvus/PG 检索

    UI->>API: POST /customer-consultations (message, thread_id, history)
    API->>API: 解析 TenantScope + require_permission(customer.consult)
    API->>SVC: create_agent_state(history + 当前消息)
    SVC->>G: build_main_graph().ainvoke(state)
    G->>G: input_security_guard -> domain_guard
    G->>ML: retrieve 知识证据
    G->>M: supervisor 意图路由（分类器/LLM/关键词）
    G->>M: 领域动作决策（结构化 JSON）
    G->>DB: 业务工具执行（工单/退款查询/申请）
    G->>M: 客服节点生成回复（可流式）
    G-->>SVC: final_state
    SVC->>DB: runtime_trace + memory + audit + conversations/messages
    SVC-->>API: CustomerConsultationResult
    API-->>UI: JSON / SSE(started,evidence,action,token,completed,done)
```

### 3.1 路由层

`backend/api/routes/customer_service.py:41` / `:127`：

1. `require_permission("customer.consult")`：
   - `AUTH_MODE=dev`：优先解析 `Authorization: Bearer <JWT>`，否则允许 `X-Tenant-Id` + `X-Actor-Id` + `X-Actor-Type` 开发 Header；
   - `AUTH_MODE=jwt-only` / `oidc`：只接受 Bearer，开发 Header 直接 401；
   - OIDC 模式下浏览器通过 `/login` 完成 Authorization Code + PKCE，后端 `/api/v1/auth/oidc/exchange` 校验 ID Token 后签发平台 JWT；
   - 校验用户存在、状态为 active、拥有对应权限。
2. `create_agent_state(...)`：把 `payload.history` 转成 `ConversationMessage` 列表，再追加当前用户消息。
3. 构造 `ConsultationKnowledgeRetriever`（带 Milvus store + reranker）与 `MemoryService`。
4. 调用 `CustomerConsultationService.run()`。

### 3.2 服务层

`backend/agent/consultation_workflow.py:166`：

1. 发出 `started` 事件（SSE）。
2. `build_main_graph(model_gateway, session_factory, event_sink, knowledge_retriever)`，编译后 `ainvoke`。
3. 发出 `completed` 事件。
4. 在 `UnitOfWork` 中依次写：
   - `runtime_traces`：一条运行轨迹；
   - `memory_records`：确定性记忆候选（可能为空）；
   - `audit_logs`：一次咨询审计；
   - `conversations` / `conversation_messages`：按 `thread_id` upsert 会话并追加本轮 user/assistant 消息；
   - `complete_runtime_trace`：写入结束状态。
5. 返回 `CustomerConsultationResult`（状态、回复、证据数、trace_id、audit ids、memory_candidate_count）。

### 3.3 SSE 事件

流式路由把 service 放进 `asyncio.create_task`，通过队列逐个 `yield`：

```
event: started    -> {thread_id, status:"started"}
event: evidence   -> {count, results:[{document_id,title,snippet,score,source}]}
event: action     -> {action, summary}
event: token      -> {text}
event: completed  -> {status, next_action, final_response}
event: done       -> {thread_id,status,next_action,final_response,knowledge_evidence_count}
event: error      -> {message:"internal server error"}
```

注意：`evidence` / `action` 事件里的 `thread_id` 当前取的是 `state.request_id`（每轮新 UUID），而 `done` 取的是业务 `thread_id`，两者不一致。前端如果依赖事件里的 `thread_id` 做关联，需要留意这个差异。

---

## 4. LangGraph 主图结构

构建入口：`backend/agent/graphs/main_graph.py:293`（`build_main_graph`）。

```mermaid
flowchart TD
    A[START] --> B[input_security_guard]
    B -->|allow| C[domain_guard]
    B -->|block/handoff| CS[customer_service_agent]
    C -->|in_scope| N[normalize_request]
    C -->|out_of_scope/clarify| CS
    N --> R[retrieve]
    R --> S[supervisor_agent]
    S -->|route_billing| BI[billing_agent]
    S -->|route_ticket| TI[ticket_agent]
    S -->|route_approval| AP[approval_agent]
    S -->|route_knowledge| KN[knowledge_agent]
    S -->|route_customer| CS
    S -->|ask_clarification / human_handoff / finish| E[END]
    BI -->|needs_policy_gate| PG[policy_gate]
    BI -->|clarify/handoff| E
    PG -->|human_handoff| E
    PG -->|continue| CS
    TI --> CS
    AP --> CS
    KN --> CS
    CS --> E
```

| 节点 | 作用 | 关键文件 |
| --- | --- | --- |
| `input_security_guard` | 输入安全边界：注入、凭据/卡号、超长、批量导出、绕过审批 | `backend/agent/nodes/guards.py:24`、`backend/agent/guards.py:43` |
| `domain_guard` | 业务范围分类；用整段对话判断，支持多轮指代 | `backend/agent/nodes/guards.py:29` |
| `normalize_request` | 空消息拒绝 | `backend/agent/graphs/main_graph.py:154` |
| `retrieve` | 调用知识检索器，产出 `knowledge_evidence`，发 `evidence` 事件 | `backend/agent/graphs/main_graph.py:42` |
| `supervisor_agent` | 意图路由（本地分类器 → LLM → 关键词） | `backend/agent/agents/supervisor.py:83` |
| `billing_agent` | 账务域动作决策 + 工具执行（退款申请、查退款/扣费） | `backend/agent/graphs/main_graph.py:89` + `backend/agent/actions.py:116` |
| `ticket_agent` | 工单域动作决策 + 工具执行（建单、查进度） | 同上 |
| `approval_agent` | 审批域动作（当前仅查退款状态） | 同上 |
| `knowledge_agent` | 结构占位；真实知识依据在 `retrieve` 已完成 | `backend/agent/graphs/main_graph.py:329` |
| `policy_gate` | 高风险退款/门禁结果转人工 | `backend/agent/policies/risk.py:51` |
| `customer_service_agent` | 唯一生成最终回复的节点；内部是子图 | `backend/agent/agents/customer_service.py:311` |

### 4.1 两套图

- `build_main_graph()` 无参数时返回 **同步骨架图**（`_build_sync_graph`），用于本地同步测试/无依赖启动，节点返回固定文案。
- 真实请求始终传 `model_gateway`、`session_factory`、`event_sink`、`knowledge_retriever`，走完整异步图。
- 领域 Agent 的独立子图（`backend/agent/agents/{billing,ticket,approval,knowledge}.py`）目前只返回 `SpecialistResult` 占位，主图并没有把它们当子图挂载；真正的业务动作在主图的 `_make_domain_node` 里通过 `ConversationActionExecutor` 执行。

### 4.2 客服子图的两种模式

`build_customer_service_graph(model_gateway, event_sink)`：

- **非流式**（无 `event_sink`）：`customer_service_model` → `response_safety_filter`；
- **流式**（有 `event_sink`）：单节点 `stream_customer_stream`，先跑守门，再逐 token 调模型并 `event_sink("token")`，最后做回复安全过滤。

因此 SSE 场景下 token 是由客服子图真正边生成边推送的，不是先生成完再切片。

---

## 5. 上下文管理

### 5.1 状态合同

`backend/agent/state.py:32`：

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| `request_id` | UUID | 单轮请求标识（也用于部分事件关联） |
| `tenant_scope` | `TenantScope` | 租户 + 操作者 + actor_type，所有仓储查询的隔离依据 |
| `conversation` | `list[ConversationMessage]` | 历史 + 当前消息 |
| `customer_id` | UUID? | 关联客户（可从 `customer_contacts` 反查） |
| `knowledge_evidence` | `list[KnowledgeEvidence]` | RAG 证据 + 业务动作结果 |
| `status` / `next_action` | str | 工作流结果/下一步 |
| `guard_decision` / `domain_decision` | Pydantic | 两层守门结论 |
| `response_draft` / `final_response` | ResponseDraft/str | 结构化回复与最终文本 |
| `model_usage` / `model_error` | ModelUsage/ModelCallError | 模型调用元数据 |
| `model_call_count` / token 累计 | int | 本轮调用次数与 token |
| `supervisor_decision` / `specialist_result` | Pydantic | 路由/专家结果 |
| `errors` / `trace_id` / `audit_event_ids` | list/UUID | 错误、轨迹、审计 |

LangGraph 节点返回 `dict`，框架按字段合并回 `AgentState`；`retrieve` 节点显式返回 `{"knowledge_evidence": evidence}` 覆盖列表。

### 5.2 对话历史从哪来

1. **前端持有**：`frontend/components/chat/chat-window.tsx` 把消息和 `threadId` 存 `localStorage`，每轮把 `messages` 映射成 `history` 一起 POST。
2. **HTTP 入参**：`CustomerConsultationRequest.history` → `_history_messages()` → `create_agent_state()`。
3. **服务端落库**：`conversations`（按 `thread_id`）+ `conversation_messages`（user/assistant 两条/轮）。
4. **服务端不回灌**：路由层没有“按 thread_id 读取历史再拼进 state”的逻辑。也就是说：
   - `/chat` 页面：前端带 `history`，多轮上下文正常；
   - `/portal/consult` 页面：只传 `thread_id + message`，不带 `history`，模型只看当前这一句（虽然服务端仍在累积落库）；
   - 直接调 API 不传 `history`：同样只有当前消息。

这是当前上下文管理最重要的边界。

### 5.3 Prompt 如何拼

`backend/agent/agents/customer_service.py:119`（`_prompt_messages`）：

1. 从 `PromptRegistry` 取 `customer_service` 模板（`backend/llm/prompt_registry.py:36`），包含“先共情、只依据证据、不盲从、不泄露、不编造业务结论”等约束。
2. 若有证据，追加：
   ```
   可用知识依据（回答必须依据这些内容，未在依据中出现的业务结论不能声称）：
   [document_id] title: snippet
   ...
   ```
   按 `max_evidence_characters` 逐条累加，超预算即停止。
3. 把 `state.conversation` 展开为“用户：… / 客服：…”的多行文本作为 `user_prompt`。
4. 分别 `truncate_text`：
   - 系统提示最多 6000 字符；
   - 证据最多 4000 字符；
   - 用户上下文最多 6000 字符。
5. 流式模式下同一套 Prompt，只是调用 `generate_stream`。

预算定义在 `backend/llm/context.py:7`，**按字符数估算，不使用真实 tokenizer**；`estimate_tokens` 仅做粗略估算（长度/2）。

### 5.4 证据（RAG）如何进入上下文

- `retrieve` 节点产出 `KnowledgeEvidence` 列表（最多 5 条）。
- 客服 Prompt 只使用 `title + content_snippet`，不注入整篇文档。
- 业务动作结果通过 `action_to_evidence()` 追加为一条 `title="业务执行结果"` 的伪文档，`score=1.0`，这样模型能“看到”刚执行的退款/工单结果，又不会把它当成知识库原文。
- 回复安全过滤器用 `has_evidence` 判断是否允许出现“退款已完成/审批通过”等业务结论。

### 5.5 长期记忆：只写不读

`backend/memory/service.py:47`：

- 每轮咨询后用 `DeterministicMemoryExtractor` 抽取偏好候选；
- `MemoryWritePolicy` 过滤：置信度 < 0.7、含凭据/卡号、含“临时/故障/待定”等瞬时词、超过 500 字 → 不写；
- 通过的写入 `memory_records`（带 TTL），Worker 的 `memory.expire` 负责过期软删。

**当前没有任何读取 `memory_records` 并注入 Prompt 的代码路径**（全仓库只有写入与过期清理）。因此“长期记忆”目前是数据采集与治理能力，不是对话上下文的一部分。

### 5.6 运行轨迹与成本

- `runtime_traces` 记录 entrypoint、状态、开始/结束时间；
- `runtime_spans` 由退款/知识等结构化工作流按节点写入；
- `tool_executions` 记录工具名、参数摘要、结果摘要、耗时；
- `audit_logs` 记录业务动作；
- `app.state.metrics` 记录 HTTP 请求计数，`/metrics` 输出 Prometheus 文本。

**已知缺口**：`AgentState` 会累计 `total_input_tokens` / `total_output_tokens`，但 `create_runtime_trace` 固定写 0，`complete_runtime_trace` 只更新状态和结束时间，**没有把 token 写回 `runtime_traces`**；因此 `/api/v1/runtime/costs` 当前显示 0。做演示时不要把它讲成“真实成本已统计”。

---

## 6. 路由与多 Agent 协作

### 6.1 三层意图路由

`backend/agent/agents/supervisor.py:71`（`route_intent`）：

1. **本地分类器**：`backend/core/query_classifier.py`，用 BGE-M3 把用户话与各领域原型句做余弦相似度；相似度 ≥ 0.6 直接采用。
   - 未配置 `BGE_M3_MODEL_PATH` 时 `_real=False`，直接返回低置信度，进入下一层；
   - 因此当前离线环境实际走的是“LLM → 关键词”。
2. **LLM 路由**：`generate_structured` 输出 `RouteDecision`（`route_billing` / `route_ticket` / `route_approval` / `route_knowledge` / `route_customer`）。
3. **关键词兜底**：`keyword_route()`，按“退款/账单/支付”“工单/投诉/故障”“审批”等关键词分流；纯“如何/怎么/政策”优先走客服。

如果 `knowledge_evidence` 里已经出现 `action-` 前缀（说明本轮已执行业务动作），关键词路由会强制回到 `route_customer`，避免二次执行。

### 6.2 两层动作决策

主图路由只决定“去哪个域”，具体动作由该域的节点再决策一次：

`backend/agent/actions.py:116`（`run_domain_action`）：

1. 每个域有允许动作白名单：
   - `route_billing`：`request_refund` / `query_refund_status` / `list_payments`
   - `route_ticket`：`create_ticket` / `query_ticket_status`
   - `route_approval`：`query_refund_status`
   - `route_knowledge` / `route_customer`：无
2. 调 `decide()`：把整段对话交给模型，输出 `ActionDecision`（action、ready、question、subject、priority）。
3. 动作不在白名单 → 不执行，回到客服回答；
4. `ready=false` 且有 `question` → 返回澄清问题，状态 `needs_clarification`；
5. 允许执行 → 用 `with_retry(...)` 包住工具执行：瞬时失败重试，最终失败降级为“无动作”，让客服仍能基于知识回答。

### 6.3 退款动作的真实执行路径

`backend/agent/actions.py:229`（`_request_refund`）：

1. 从 `customer_contacts` 反查当前用户关联的 `customer_id`；
2. 查最近 10 笔成功支付；
3. 找 **24 小时内同金额** 的重复扣费；
4. 找不到 → 如实告知“未发现重复扣费”，**不发起退款**；
5. 找到 → `BillingTool.request()` 创建本地退款申请，幂等键 `chat-refund-{payment_id}`；
6. 结果包装成 `ActionResult`，再转成证据注入回复。

对话里的退款不直接调用 `RefundWorkflowService`，而是走 `BillingTool.request()`；后者只创建 `refunds` 记录，不会自动进入审批。结构化退款接口 `POST /api/v1/refunds` 才走完整的 `RefundWorkflowService`（policy gate + 审批 Checkpoint）。

### 6.4 审批恢复

`backend/agent/approval_workflow.py:25`（`resume_refund_after_approval`）：

1. 取审批单，必须 `pending`；
2. 取 `workflow_checkpoints`（按 `thread_id`）；
3. 写 `approval_actions`；
4. 写审计 `refund_approval_approved/rejected`；
5. 更新 Checkpoint 状态为 `approved_for_execution` / `rejected`；
6. 完成 Runtime Trace。

注意：**“审批通过”只表示本地状态允许继续执行，并不代表真实资金已到账**；代码里也没有自动调用外部支付网关。

---

## 7. 工具调用机制

### 7.1 不是 Function Calling

模型不直接拿工具 schema 去发起 tool call。实际机制是：

```
模型输出结构化 JSON（action/ready/subject...）
        ↓
后端 Pydantic 校验（ActionDecision）
        ↓
白名单校验 + 租户上下文解析
        ↓
Python 工具类方法（BillingTool / TicketTool / KnowledgeTool）
        ↓
UnitOfWork 仓储写库 + 审计 + ToolExecution
```

好处是可控、可审计、不会出现模型幻觉参数直接落库；代价是新增工具要同时改“动作枚举 + 白名单 + 执行分支”。

### 7.2 工具注册表 vs 实际工具

`backend/agent/tools/base.py:41` 的 `ToolRegistry` 只是**元数据目录**（name / owner_agent / description），供 `AgentRegistry.allowed_tools` 和测试使用；主图实际调用的是工具类方法，不经过这个 Registry 的动态派发。

`backend/agent/registry.py:40` 的 `AgentRegistry` 同样偏“声明式清单”，主图没有用它来动态挂载子图。

### 7.3 工具清单

| 工具/动作 | 实现 | 作用 | 副作用 | 幂等/审批 |
| --- | --- | --- | --- | --- |
| `billing.preview` | `BillingTool.preview` | 校验退款金额、支付归属，返回预览 | 只读 | 无 |
| `billing.request` | `BillingTool.request` | 创建本地退款申请 | 写 `refunds` | 幂等键按租户唯一 |
| `billing.execute` | `BillingTool.execute` | 审批后执行（当前仍走 request） | 写 `refunds` | 必须 `approved=True` |
| `ticket.create` | `TicketTool.create` | 创建工单 + 首条消息 | 写 `tickets`/`ticket_messages` | 无 |
| `ticket.update` | `TicketTool.update` | 工单状态流转 | 写 `tickets`/`ticket_events` | 状态机校验 |
| `knowledge.search` | `KnowledgeTool.search` | PG 关键词检索文档 | 只读 | 无 |
| `approval.request` | `SupportRepository.create_refund_approval_request` | 创建退款审批单 | 写 `approval_requests` | 与退款同事务 |
| `approval.status` | `SupportRepository.get_approval_request_for_tenant` | 查审批状态 | 只读 | 无 |
| 会话动作 `request_refund` | `ConversationActionExecutor._request_refund` | 识别重复扣费并发起退款 | 写 `refunds` | 幂等键 `chat-refund-{payment_id}` |
| 会话动作 `create_ticket` | `_create_ticket` | 从对话直接建单 | 写 `tickets` | 无 |
| 会话动作 `list_payments` | `_list_payments` | 查最近支付 | 只读 | 无 |
| 会话动作 `query_ticket_status` | `_query_ticket_status` | 查最近工单 | 只读 | 无 |
| 会话动作 `query_refund_status` | `_query_refund_status` | 查最近退款 | 只读 | 无 |
| MCP `search_knowledge` | `backend/mcp/knowledge_base_server.py:47` | 通过 MCP 暴露知识检索 | 只读 | 需安装 `mcp` |
| MCP `web_search` | `backend/mcp/web_search_server.py:46` | Tavily/DuckDuckGo 搜索 | 外部网络 | 需安装 `mcp` + 可选 `duckduckgo-search` |

### 7.4 租户隔离与事务

- 所有工具方法第一参数都是 `scope: TenantScope`；
- `UnitOfWork` 统一持有 `identity/billing/support/governance/knowledge/evaluation/runtime` 七个仓储；
- 仓储方法用 `tenant_id` 过滤；跨租户写入在数据库层还有复合外键/唯一约束兜底；
- `UnitOfWork.__aexit__` 正常提交、异常回滚；
- 审计与业务写入通常在同一个 UoW 内，保证“动作 + 留痕”一致。

### 7.5 新增一个工具的步骤

1. 在 `backend/agent/tools/` 新增 Tool 类与请求/结果 Pydantic 模型；
2. 在 `backend/agent/actions.py` 的 `ActionDecision.action` Literal 中加动作；
3. 在 `_DOMAIN_ACTIONS` 把动作挂到对应域白名单；
4. 在 `execute()` 增加分支与实现（内部用 UoW + scope）；
5. 在 `backend/agent/tools/base.py` 注册元数据（供清单/测试）；
6. 补 `tests/unit/agent/` 与 `tests/integration/agent/` 回归；
7. 如需对外暴露，再在 `backend/api/routes/` 增加 HTTP 端点并加 `require_permission`。

---

## 8. RAG 知识链路

### 8.1 写入（摄取）

`POST /api/v1/knowledge/documents` → `KnowledgeIngestService`（`backend/rag/ingestion.py:55`）：

1. 用 `InputSecurityGuard` 检查标题+正文；
2. 按 `chunk_size=800`、`chunk_overlap=80` 切片；
3. 写 `documents` + `document_versions` + `knowledge_chunks`；
4. 若配置了 `MILVUS_URI`，同步 `upsert_document_chunks` 到 Milvus；
5. 写审计与 Runtime Trace。

### 8.2 读取（咨询检索）

`ConsultationKnowledgeRetriever.retrieve`（`backend/rag/retriever.py:26`）：

1. 有向量库：Milvus 召回 top-k；
2. 同时跑 PG 关键词检索；
3. 若 Milvus 无命中 → 直接返回 PG 结果（这是 9368e8a 修复的回退逻辑）；
4. 有命中 → 用 **RRF** 合并（`backend/rag/hybrid.py:14`，常数 60），按 RRF 分数排序；
5. 若配置了 `RERANKER_MODEL_PATH` → Cross-Encoder 精排；否则确定性按分数排序；
6. 产出 `KnowledgeEvidence`，最多 5 条进入 Prompt。

### 8.3 检索接口

`GET /api/v1/knowledge/search` 走 `KnowledgeWorkflowService`（`backend/agent/knowledge_workflow.py:62`），它是“文档级”结果（title/snippet/score），同样先向量再 PG，再 RRF 合并；与咨询检索共用底层思路，但返回结构不同。

### 8.4 当前降级行为

- 无 `MILVUS_URI`：纯 PG 标题/关键词检索；
- Milvus 连接失败：`retrieve` 外层 try/except 吞掉异常，返回空证据，不阻断对话；
- 无 BGE-M3：确定性离线 Embedding（384 维），不下载模型、不访问外网；
- 无 Reranker：确定性排序。

> 已修复（2026-10-21）：
> - Milvus COSINE 对不相关文本可能返回微弱负分（如 `-0.0127`），而 `KnowledgeEvidence.score` 要求 `0..1`，导致整个检索构造证据时抛 `ValidationError`，又被上层静默吞掉，表现为“知识库有文档但咨询永远 0 条证据”。现在在 `backend/rag/retriever.py` 统一把分数截断到 `0..1`，并新增 `tests/unit/rag/test_retriever.py::test_negative_vector_score_is_clamped` 回归测试。
> - 同一 `external_document_id` 重复摄取时，旧 chunk 删除与新 chunk 插入在同一次 flush 中执行，会撞 `(tenant_id, document_id, chunk_number)` 唯一约束。现在先 flush 删除再插入，并新增 `tests/integration/database/test_knowledge_ingestion.py::test_reingesting_same_document_replaces_chunks`。
> - `httpx` 0.28 会把 `NO_PROXY` 中的 `[::1]` 展开为非法模式 `all://*[::1]`，导致构造 `httpx.AsyncClient()` 抛 `InvalidURL`。`DeepSeekGateway` 现在在创建客户端前清理带方括号的 IPv6 条目，并新增 `tests/unit/llm/test_deepseek_proxy.py`。

---

## 9. 安全边界

| 层 | 位置 | 拦截内容 | 结果 |
| --- | --- | --- | --- |
| 输入安全 Guard | `backend/agent/guards.py:43` | Prompt Injection、`sk-`/Bearer/密码/卡号、超长（>2000）、批量导出/跨租户索取、绕过审批 | `block` 或 `human_handoff` |
| 业务范围 Guard | `backend/agent/guards.py:121` | 真实生产资金/转账、非 CloudDesk 平台、外部系统 | `out_of_scope` / `needs_clarification` |
| 退款策略门禁 | `backend/agent/policies/risk.py:31` | 支付未成功、金额非法、未知执行状态；≥1000 元或非 user 操作者需审批 | 拒绝或转审批 |
| 回复安全过滤 | `backend/llm/safety.py:51` | 凭据/内部提示/数据库地址、超长、无证据却声称“退款完成/审批通过” | `block` 或 `human_handoff` |
| 知识摄取 Guard | `backend/rag/ingestion.py:61` | 同上输入安全规则 | 阻止入库 |
| 租户隔离 | `TenantScope` + 复合外键 | 跨租户读写 | 查询为空/写入失败 |
| 脱敏 | Checkpoint/审计/Trace | 只存摘要与哈希，不存原始 Prompt/Key/知识原文 | — |

一个容易误解的点：`domain_guard` 用**整段对话**判断业务范围，而 `input_security_guard` 只看**最新一条用户消息**。这是有意设计：安全边界不能被历史“洗白”，业务范围则需要多轮上下文。

---

## 10. 持久化与可观测

| 表 | 写入时机 | 内容 |
| --- | --- | --- |
| `runtime_traces` | 每次咨询/退款/知识/工单工作流 | entrypoint、状态、起止时间 |
| `runtime_spans` | 结构化工作流的节点级记录 | node_name、状态、摘要 |
| `tool_executions` | 工具执行后 | tool_name、参数摘要、结果摘要、耗时 |
| `audit_logs` | 业务动作/拦截/审批 | action、resource、metadata 摘要+hash |
| `conversations` / `conversation_messages` | 每轮咨询后 | thread_id、渠道、user/assistant 消息 |
| `workflow_checkpoints` | 退款申请/审批恢复 | state_summary、幂等键、状态、trace_id |
| `memory_records` | 每轮咨询后 | 记忆候选、置信度、TTL |
| `approval_requests` / `approval_actions` | 高风险退款 | 审批单、动作、理由 |

`/metrics` 目前只有 HTTP 请求计数；Prometheus/Grafana 的完整栈在 `infra/` 与 `docker-compose.yml` 中，当前未启动。

---

## 11. 当前实现边界（演示时不要过度承诺）

1. **模型**：本机已配置真实 Key，走 DeepSeek；未配 Key 时自动回退 `FakeModelGateway`（固定模板）。
2. **多轮上下文**：服务端不回灌历史；只有前端 `/chat` 会带 `history`，`/portal/consult` 与裸 API 不带。
3. **长期记忆**：只写不读，不进入 Prompt。
4. **知识 Agent**：主图里是空节点；真实知识依据在 `retrieve` 阶段完成，`knowledge_agent` 不做独立工具调用。
5. **领域 Agent 子图**：`billing/ticket/approval/knowledge` 的 `build_*_graph` 只是占位；主图实际用 `ConversationActionExecutor`。
6. **对话内退款的审批关联**：对话内退款现在会为 ≥1000 元的退款创建审批单和 Checkpoint，但 Checkpoint 的 reference 当前使用本轮 `request_id`，不是 conversation `thread_id`；审批页面会用它作为 `thread_id`，流程可用，但审计关联与对话 thread_id 不同。
7. **MCP**：可选依赖未安装，`/mcp/kb`、`/mcp/web-search` 未挂载；`backend/mcp/client.py` 也未被主流程调用。
8. **BGE-M3 / Reranker**：模型文件不存在，当前是确定性离线 Embedding + 确定性排序。
9. **成本统计**：Token 已写回 `runtime_traces`（新生成的咨询 Trace 有输入/输出 Token）；但未配置计价规则，成本显示 `—`，不伪造金额。
10. **真实资金**：退款完成只代表本地申请/审批/审计落库，不代表第三方到账；Billing/CRM 等仍是 Mock。
11. **认证**：本地已实现 OIDC（Dex）+ `AUTH_MODE=dev/jwt-only/oidc`；`oidc` 模式禁用开发 Header 与 `/auth/tokens`。生产仍需替换为企业 IdP，并把前端 JWT 存储升级为 HttpOnly Cookie + CSRF 防护，同时补齐全路由 RBAC 矩阵。
12. **Redis/Worker**：未启动；只影响记忆过期等异步维护，不影响聊天主链路。
13. **SSE 事件 `thread_id`**：`evidence`/`action` 用 `request_id`，`done` 用业务 `thread_id`，不一致。

---

## 12. 本地验证清单

### 12.1 当前可用的验证

```powershell
# 健康检查
Invoke-RestMethod http://127.0.0.1:8080/healthz

# 租户/用户
Invoke-RestMethod http://127.0.0.1:8080/api/v1/identity/tenants

# 咨询（开发 Header）
$h = @{
  "X-Tenant-Id" = "<tenant_id>"
  "X-Actor-Id"  = "<user_id>"
  "X-Actor-Type"= "user"
}
$body = @{ message="你好，退款政策是什么？"; thread_id="demo-1" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/v1/customer-consultations `
  -Headers $h -ContentType "application/json" -Body $body

# SSE（观察 started/evidence/token/completed/done）
curl.exe -N -X POST http://127.0.0.1:8080/api/v1/customer-consultations/stream `
  -H "Content-Type: application/json" -H "X-Tenant-Id: <tenant_id>" `
  -H "X-Actor-Id: <user_id>" -H "X-Actor-Type: user" `
  -d '{\"message\":\"你好\",\"thread_id\":\"demo-sse\"}'
```

### 12.2 前端页面

- `/` → 重定向 `/chat`
- `/login` → 企业账号登录（OIDC Authorization Code + PKCE）
- `/auth/callback` → OIDC 回调，后端换取会话后进入 `/chat`
- `/identity` → 开发身份选择器（仅 `AUTH_MODE=dev` 可用）
- `/chat`、`/workspace`、`/admin`、`/portal/consult` 均返回 200

### 12.3 常用后端接口

| 接口 | 权限 |
| --- | --- |
| `POST /api/v1/customer-consultations` | `customer.consult` |
| `POST /api/v1/customer-consultations/stream` | `customer.consult` |
| `POST/GET /api/v1/tickets` | `ticket.create` / `ticket.read` |
| `POST /api/v1/refunds` | `refund.request` |
| `GET/POST /api/v1/approvals` | `approval.read` / `refund.approve` |
| `GET /api/v1/knowledge/search` | `knowledge.search` |
| `POST /api/v1/knowledge/documents` | `knowledge.ingest` |
| `GET /api/v1/runtime/traces` | `runtime.read` |
| `POST /api/v1/evaluations/run` | `evaluation.run` |

### 12.4 已预置的最小演示数据

脚本：`scripts/seed_demo_minimal.py`（可重复执行；租户/用户/客户/支付/工单不会重复创建，知识文档会新增版本）。

| 对象 | ID / 值 |
| --- | --- |
| 租户 | `c7904418-85be-41a2-97bc-0a7ab4431518`（slug `clouddesk`） |
| 用户 | `057e4bc8-b224-4d02-b755-cf673f72fed6`（`demo@clouddesk.local`） |
| 客户 | `fe7dc185-6816-44e3-892f-ce8fbdcabd4c`（`演示客户（脱敏）`） |
| 工单 | `b65a4557-9a2a-463e-9ad9-10be19a5fb43`（账单金额疑问，`in_progress`） |
| 普通支付 | `090dab28-62b2-4927-83c5-6393fe432a30`（99 元） |
| 重复扣费支付 | `00afef10-40ba-4172-8b31-accac59afc7f` / `e6c47abd-625d-4ad0-8bbd-7a6247d60d40`（各 1280 元，间隔 4 小时） |
| 知识文档 | `demo-kb-refund`、`demo-kb-sla`、`demo-kb-invoice`（已写入 PG + Milvus） |

已实测通过的链路：

1. `GET /api/v1/knowledge/search?q=退款政策` → 3 条，退款政策排第一；
2. `POST /api/v1/customer-consultations` 问退款政策 → `knowledge_evidence_count=3`；
3. `POST /api/v1/refunds`（1280 元）→ `awaiting_approval`，生成审批单 `9c24e6e3-d1ae-459a-aef6-7998c47847e6`；
4. `POST /api/v1/approvals/{id}` 通过 → `approved_for_execution`；
5. `GET /api/v1/tickets` → 1 条；`GET /api/v1/runtime/traces` → 咨询/退款/知识摄取轨迹均有记录。
6. 真实 DeepSeek（`provider=deepseek`）：普通咨询约 2.9s 返回自然语言；SSE 逐 token 推送；`final_response` 已去除 JSON 外壳。
7. 真实 DeepSeek + 工具：说“我被重复扣费了，请帮我退款” → `action=request_refund`，创建退款单与审批单；用审批页返回的 `checkpoint_reference` 作为 `thread_id` 审批 → `approved_for_execution`。

> 重复扣费支付对用于对话里的 `request_refund` 场景；1280 元 ≥ 1000 元，也用于演示“高金额退款必须人工审批”。

---

### 12.5 浏览器彩排结果（2026-10-21）

使用 Playwright + Chromium 以 1440×960 走完：

1. `/identity` 选择 `clouddesk` → `演示管理员`；
2. `/chat` 发送真实问题 → 真实模型流式回复；
3. 打开“上下文”抽屉 → 知识证据卡片正常；
4. `/workspace/approvals` → 待审批列表出现“退款审批 / ¥1280.00 / 高风险 / 财务经理”；
5. 进入审批详情 → 批准 → 确认 → 状态变为“已批准”；
6. `/admin/runtime` → 咨询/退款/知识轨迹可见；
7. `/workspace/knowledge` → 知识检索页正常。

结果：**无浏览器 console error、无 page error、无真实请求失败**（仅 Next.js 预取在跳转时被取消，属正常现象）。截图保存在 `output/ui-rehearsal/`（`01`~`12`）。

当前演示状态：保留了一张待审批单 `5456681e-d2b1-44e9-a183-57e976451ab5`（退款审批，1280 元），供演示直接从审批队列进入。

### 12.6 演示前 60 秒检查清单

- [ ] `http://127.0.0.1:8080/healthz` 返回 `{"status":"ok"}`
- [ ] `http://127.0.0.1:3000/identity` 能列出租户
- [ ] `/workspace/approvals` 至少有 1 条待审批
- [ ] `/chat` 发一句话能在 10 秒内出字
- [ ] 浏览器没有红色报错、页面没有 “Fake”/JSON 残留
- [ ] `.env` 不在投屏范围，浏览器标签页不暴露终端

## 13. 关键文件索引

| 主题 | 文件 |
| --- | --- |
| FastAPI 应用/路由挂载 | `backend/main.py` |
| 咨询 HTTP/SSE | `backend/api/routes/customer_service.py` |
| 咨询工作流/持久化 | `backend/agent/consultation_workflow.py` |
| 主图 | `backend/agent/graphs/main_graph.py` |
| 状态合同 | `backend/agent/state.py` |
| 输入/业务守门 | `backend/agent/guards.py`、`backend/agent/nodes/guards.py` |
| 主管路由 | `backend/agent/agents/supervisor.py` |
| 客服生成/安全过滤 | `backend/agent/agents/customer_service.py` |
| 动作决策/工具执行 | `backend/agent/actions.py` |
| 业务工具 | `backend/agent/tools/{billing,ticket,knowledge}.py` |
| 退款策略门禁 | `backend/agent/policies/risk.py` |
| 退款工作流 | `backend/agent/refund_workflow.py` |
| 审批恢复 | `backend/agent/approval_workflow.py` |
| Checkpoint | `backend/agent/checkpoint.py` |
| Prompt 注册表 | `backend/llm/prompt_registry.py` |
| 上下文预算 | `backend/llm/context.py` |
| 回复安全 | `backend/llm/safety.py` |
| 模型网关 | `backend/llm/{gateway,deepseek,fake,factory,router}.py` |
| 知识检索 | `backend/rag/retriever.py`、`hybrid.py`、`reranker.py`、`vector_store.py` |
| 知识摄取 | `backend/rag/ingestion.py` |
| 记忆 | `backend/memory/{service,policy,candidates}.py` |
| MCP | `backend/mcp/{knowledge_base_server,web_search_server,client}.py` |
| 事务/租户 | `backend/database/unit_of_work.py`、`backend/database/base.py` |
| 观测 | `backend/observability/metrics.py`、`backend/api/routes/runtime.py` |
