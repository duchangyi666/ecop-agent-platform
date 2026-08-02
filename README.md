# 企业级客户运营平台

这是一个与现有项目完全独立的企业级智能客服与工单处理 Agent 平台。当前已完成领域模型、PostgreSQL 数据库、租户隔离、事务边界、Alembic 迁移，以及输入安全 Guard、业务范围 Guard、Supervisor + 五个专属 Agent 的 LangGraph 多智能体工作流。退款链路已具备数据库持久化申请、审批 Checkpoint 和审批恢复能力。

## 当前技术基线

- Python：以本机 `edu_agent` 环境实际版本为准
- SQLAlchemy：2.0.36
- Pydantic：2.11.4
- LangGraph：1.0.9
- PostgreSQL：项目专用 Docker 容器，映射端口 `54329`
- pymilvus：2.4.9（RAG 向量存储；BGE-M3 使用可选 `sentence-transformers`）
- Alembic 当前迁移头：`006_knowledge_chunks`
- 数据库连接：`postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations`

## 启动数据库与验证

在项目根目录执行：

```powershell
docker compose -f infra/compose/docker-compose.db.yml up -d postgres
$env:PYTHONNOUSERSITE = "1"
& E:\anaconda3\envs\edu_agent\python.exe -m alembic upgrade head
& E:\anaconda3\envs\edu_agent\python.exe scripts/verify_database.py
& E:\anaconda3\envs\edu_agent\python.exe -m pytest tests/unit tests/integration/database -q
```

验证多智能体工作流：

```powershell
$env:PYTHONNOUSERSITE = "1"
& E:\anaconda3\envs\edu_agent\python.exe -m pip check
& E:\anaconda3\envs\edu_agent\python.exe -m pytest tests/unit tests/integration/database tests/integration/agent tests/integration/api tests/integration/vectorstore -q
& E:\anaconda3\envs\edu_agent\python.exe -m compileall -q backend scripts
& E:\anaconda3\envs\edu_agent\python.exe -m alembic check
```

如需显式指定连接串：

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations"
```

## HTTP API（开发环境）

启动独立 FastAPI 应用：

```powershell
$env:PYTHONNOUSERSITE = "1"
$env:DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations"
& E:\anaconda3\envs\edu_agent\python.exe -m uvicorn backend.main:app --reload
```

当前已提供：

- `GET /healthz`：应用存活检查；
- `POST /api/v1/customer-consultations`：调用主图生成客户咨询安全回复；
- `POST /api/v1/customer-consultations/stream`：以 SSE 推送客户咨询开始、证据检索和完成事件；
- `POST /api/v1/auth/tokens`：为当前租户活动用户签发本地 JWT Bearer Token；
- `GET /api/v1/evaluations`：查看当前租户评测运行；
- `POST /api/v1/evaluations/run`：运行检索评测并返回 Recall@K、MRR、NDCG；
- `POST /api/v1/tickets`：创建租户作用域工单；
- `GET /api/v1/knowledge/search`：检索当前租户 active 知识文档；
- `POST /api/v1/knowledge/documents`：摄取知识文档、分片并写入 Milvus 向量索引；
- `POST /api/v1/refunds`：提交本地退款申请；
- `POST /api/v1/approvals/{approval_request_id}`：批准或拒绝退款审批；
- `GET /api/v1/workflows/{thread_id}`：按租户查询脱敏工作流状态。

业务请求需要携带开发环境 Header：`X-Tenant-Id`、`X-Actor-Id`、`X-Actor-Type`，可选 `X-Request-Id`。这些 Header 只用于当前本地开发和集成测试，不等同于生产 JWT/OAuth 认证。客户咨询需要 `customer.consult`，工单创建需要 `ticket.create`，知识检索需要 `knowledge.search`，知识摄取需要 `knowledge.ingest`，退款接口需要 `refund.request` / `refund.approve`，评测需要 `evaluation.read` / `evaluation.run`。接口详细合同见 [`docs/superpowers/specs/2026-08-02-退款业务HTTP API设计.md`](docs/superpowers/specs/2026-08-02-退款业务HTTP%20API设计.md) 和 [`docs/superpowers/specs/2026-08-02-客户咨询API与模型网关工厂设计.md`](docs/superpowers/specs/2026-08-02-客户咨询API与模型网关工厂设计.md)。

## 本地 JWT 认证

设置 `JWT_SECRET` 后可启用本地签名 Token；业务接口同时接受 `Authorization: Bearer <token>`，未传 Token 时仍允许开发 Header 降级。

```powershell
$env:JWT_SECRET = "<至少32字节的本地密钥>"
$env:JWT_TOKEN_EXPIRES_MINUTES = "60"
```

获取本地开发 Token：

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/auth/tokens `
  -ContentType "application/json" `
  -Body '{"tenant_id":"<租户UUID>","user_id":"<用户UUID>","actor_type":"user"}'
```

Token 只包含租户、用户、角色类型、签发时间和过期时间，不包含密钥或敏感数据；过期后返回 HTTP 401。这是本地 JWT 认证边界，不代表已接入真实 OAuth、SSO 或生产身份提供商。

## Guard 与安全边界

请求进入主图后按固定顺序经过 `input_security_guard` 和 `domain_guard`，再进入 `normalize_request`、Supervisor、专属 Agent 和策略门禁：

- Prompt Injection、凭据/银行卡号、超长输入：返回 `blocked`，不重试、不调用业务工具；
- 绕过审批、租户隔离或未授权工具：返回 `human_handoff`，转人工安全审核；
- 真实生产资金、外部系统等越界请求：返回 `out_of_scope`；
- 无法判断业务场景：返回 `needs_clarification`，下一动作是 `ask_clarification`；
- 退款服务只有在安全状态为 `allow`、业务域为 `billing` 时才会读取 Payment 或执行 `billing.preview` / 退款申请；
- 工单服务只有在安全状态为 `allow`、业务域为 `ticket` 时才会执行 `ticket.create` / `ticket.update`；
- 知识检索服务只查询当前租户 `active` 文档；未配置 Milvus 时回退到 PostgreSQL 标题检索，配置后使用租户过滤的向量召回。

## RAG 向量知识库

项目新增可降级的 RAG 基础层：`POST /api/v1/knowledge/documents` 会把知识内容分片后写入 PostgreSQL `knowledge_chunks`，并同步到 Milvus 向量集合；`GET /api/v1/knowledge/search` 在配置 `MILVUS_URI` 时使用 Milvus 向量召回与 PostgreSQL 关键词检索的 RRF 混合结果，未配置时只使用 PostgreSQL 标题检索。

客户咨询 API 已接入同一检索链路：模型生成前先按当前租户检索知识证据，证据摘要进入模型 Prompt，响应中的 `knowledge_evidence_count` 只报告命中数量，不返回知识原文。

## SSE 进度事件

`POST /api/v1/customer-consultations/stream` 使用 `text/event-stream` 返回事件流：

- `started`：工作流开始；
- `evidence`：知识证据检索完成，`count` 只报告数量；
- `completed`：结构化生成和安全审查完成；
- `done`：最终脱敏摘要。

SSE 不推送模型 Token、思维链、系统 Prompt、Key 或知识原文；断流时取消当前工作流任务。

## 本地前端控制台

FastAPI 会直接托管 `frontend/` 静态控制台，启动后端后访问：

```text
http://localhost:8000/
```

控制台提供本地演示所需的最小交互：填写租户/用户 UUID 获取 JWT Token、检索当前租户知识文档、发送客户咨询并展示 SSE 进度事件。它不包含完整 Customer Portal、Support Workspace 或 Admin Console，也不是生产级 Next.js 前端。

## 评测系统

`POST /api/v1/evaluations/run` 基于 `evaluation_datasets` 和 `evaluation_cases` 运行检索评测，对每个用例调用当前检索链路，并计算：

- `Recall@K`
- `Precision@K`
- `MRR`
- `NDCG@K`

每个用例的指标写入 `evaluation_results`，运行汇总写入 `evaluation_runs.metrics`；`GET /api/v1/evaluations` 可查看当前租户评测历史。当前评测聚焦检索链路，分类、决策、工具和回复评测仍属于后续阶段。

基于当前租户 active 文档生成一个简单检索评测集：

```powershell
$env:PYTHONNOUSERSITE = "1"
& E:\anaconda3\envs\edu_agent\python.exe scripts/seed_evaluation.py `
  --tenant-id <租户UUID> `
  --dataset-code tenant-retrieval `
  --name "Tenant Retrieval Dataset"
```

## 长期记忆

客户咨询完成后，`MemoryService` 会从对话中提取稳定的偏好候选，例如语言偏好、时区和用户偏好；`MemoryWritePolicy` 拒绝低置信度、瞬时状态、凭据和过短内容。候选记忆只保存脱敏摘要和哈希，不保存原始聊天内容、最终回复或系统 Prompt。

客户咨询响应中的 `memory_candidate_count` 只报告本次写入的候选数量，不返回记忆正文。

## 模型路由、Prompt Registry 与上下文预算

`ModelRouter` 按任务解析模型路由，默认从环境变量读取：

```powershell
$env:MODEL_ROUTE_MODEL = "deepseek-v4-flash"
$env:MODEL_ROUTE_PROVIDER = "deepseek"
```

`PromptRegistry` 保存版本化 Prompt 模板，当前内置客服 Prompt；`ContextBudget` 在模型调用前对知识证据和系统 Prompt 做本地字符预算限制，防止无限拼接上下文。

当前路由和预算主要作用于客户咨询链路；完整 Model Router 调用、Prompt 管理 API 和 DB 持久化 Prompt 版本仍属于后续阶段。

启动项目专用 Milvus 栈：

```powershell
docker compose -f infra/compose/docker-compose.rag.yml up -d
$env:MILVUS_URI = "http://localhost:19541"
```

当前本地验证也可以复用已运行的 Milvus 实例，例如：

```powershell
$env:MILVUS_URI = "http://localhost:19531"
```

默认 Embedding 使用确定性的离线向量，不下载模型、不访问外网。如需使用 BGE-M3，指定本地模型目录：

```powershell
$env:BGE_M3_MODEL_PATH = "D:\models\BAAI\bge-m3"
```

精排默认使用确定性 RRF 得分排序；如需启用 Cross-Encoder，指定本地模型目录：

```powershell
$env:RERANKER_MODEL_PATH = "D:\models\BAAI\bge-reranker-large"
```

本阶段不保存原始知识正文到审计、日志或运行轨迹；搜索响应只返回文档摘要、RRF 得分和最多 300 字的分片摘要。尚未接入 BGE-M3 默认加载、稀疏向量召回或真实 Cross-Encoder 模型验证。

Guard 终止结果会写入同一租户的 `AuditLog`、`RuntimeTrace` 和 `WorkflowCheckpoint`。检查点和对外响应不保存或回显敏感原文。Guard 使用当前仓库已安装的确定性 Python/Pydantic 规则，不代表已经接入 LLM 安全分类器、Redis、第三方支付或正式 JWT/OAuth。

## 模型网关与结构化客服回复

客服子图已接入 provider-neutral 的 `ModelGateway` 契约：

- `DeepSeekGateway` 使用项目实际安装的 `httpx==0.28.1` 调用 OpenAI-compatible Chat Completions；
- `FakeModelGateway` 是默认离线实现，主图和自动测试不会读取环境变量、创建外网连接或依赖真实模型 Key；
- 模型只能生成 Pydantic `ResponseDraft`，随后由 `ResponseSafetyFilter` 检查敏感信息、内部配置和缺少依据的业务承诺；
- 模型异常、敏感输出和未经证据支持的业务结论会返回固定安全回复或转人工，不会触发退款、审批、工单或数据库工具；
- `DEEPSEEK_API_KEY` 只允许从运行时环境变量读取，仓库、测试、日志和文档不保存 Key、完整 Prompt 或模型响应原文。

应用启动时通过 `backend/llm/factory.py` 的 `create_model_gateway()` 创建网关并放入 FastAPI `app.state`：

- 没有 `DEEPSEEK_API_KEY` 时默认创建 `FakeModelGateway`，本地启动和自动测试不访问外网；
- 显式配置 `DEEPSEEK_API_KEY` 时才创建 `DeepSeekGateway`；
- 客户咨询 API 从 `app.state` 读取同一个应用级 Gateway，不在请求内临时构造外部客户端；
- 测试或本地演示可通过 `create_app(model_gateway=FakeModelGateway(...))` 显式注入离线网关。

如需在本机显式接入模型，先设置环境变量；自动回归不执行真实 API 冒烟请求：

```powershell
$env:DEEPSEEK_API_KEY = "<仅保存在本机进程环境中的新 Key>"
$env:DEEPSEEK_BASE_URL = "https://api.deepseek.com"
$env:DEEPSEEK_MODEL = "deepseek-v4-flash"
```

当前阶段只完成模型网关、结构化回复、输出安全边界、RAG 向量检索基础、SSE 进度事件、本地 JWT 认证和本地静态控制台，尚未接入正式 OAuth/SSO、生产级 Next.js 前端或第三方支付。模型不能直接执行数据库写入和业务工具。

为开发用户授予退款权限：

```powershell
$env:PYTHONNOUSERSITE = "1"
$env:DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations"
& E:\anaconda3\envs\edu_agent\python.exe scripts\seed_demo_identity.py `
  --tenant-id <租户UUID> `
  --user-id <用户UUID> `
  --permissions refund.request refund.approve customer.consult ticket.create knowledge.search knowledge.ingest evaluation.read evaluation.run
```

该脚本只允许声明的五个权限码，并且重复执行幂等；仅用于开发和测试，不替代生产认证、角色审批和密钥管理。

## 目录说明

- `backend/domain`：支付、退款、工单和审批状态机
- `backend/database/models`：身份、计费、工单、治理和评测模型
- `backend/database/repositories`：租户作用域 Repository
- `backend/database/unit_of_work.py`：事务边界与 Repository 组合
- `backend/rag`：Embedding、文本分片、Milvus 向量存储和知识摄取服务
- `backend/evaluation`：检索评测指标和评测 Runner
- `backend/memory`：确定性记忆提取、写入策略和候选记忆服务
- `backend/llm`：模型网关、结构化回复、安全过滤、模型路由、Prompt Registry 和上下文预算
- `frontend`：由 FastAPI 静态托管的本地演示控制台
- `alembic/versions`：数据库迁移链
- `scripts/verify_database.py`：数据库结构和迁移头验收
- `docs/architecture`：中文领域模型、数据库、事务、Guard、多智能体工作流和退款审批闭环文档
- `docs/superpowers/specs`：模型网关、Guard、退款业务和客户咨询 API 合同
- `docs/验证记录`：按实际 Python 环境和数据库容器生成的验收证据

## 约束

普通业务查询必须携带 `TenantScope`；金额使用 `Decimal` 和 `NUMERIC(18, 2)`；退款幂等键按租户隔离；敏感 payload 只保存脱敏摘要。计费 Agent 必须经过策略门禁，未知支付执行状态转人工处理。

退款链路的“完成”仅表示本地退款申请、`Refund`、审批动作、审计事件和运行 Checkpoint 已写入 PostgreSQL；当前不调用第三方支付网关，因此不代表第三方资金已经到账。详细时序见 [`docs/architecture/数据库驱动退款审批闭环.md`](docs/architecture/数据库驱动退款审批闭环.md)。
