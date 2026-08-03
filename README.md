# 企业级客户运营平台

这是一个与现有项目完全独立的企业级智能客服与工单处理 Agent 平台。当前已完成领域模型、PostgreSQL 数据库、租户隔离、事务边界、Alembic 迁移，以及输入安全 Guard、业务范围 Guard、Supervisor + 五个专属 Agent 的 LangGraph 多智能体工作流。退款链路已具备数据库持久化申请、审批 Checkpoint 和审批恢复能力。

## 当前技术基线

- Python：以本机 `edu_agent` 环境实际版本为准
- SQLAlchemy：2.0.36
- Pydantic：2.11.4
- LangGraph：1.0.9
- PostgreSQL：项目专用 Docker 容器，映射端口 `54329`
- pymilvus：2.4.9（RAG 向量存储；BGE-M3 使用可选 `sentence-transformers`）
- Alembic 当前迁移头：`009_conversation_thread`
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

## 生成企业级 Synthetic Data

`scripts/generate_synthetic_data.py` 生成业务一致的模拟企业数据，覆盖规格第 25 节的完整租户图谱，满足全部外键、唯一约束和领域状态机。规模可配置：

- `--scale small`：10 租户 / 600 用户 / 200 客户 / 1200 支付 / 600 工单 / 1000 评测用例，适合快速验证。
- `--scale full`：50 租户 / 5 万用户 / 1 万客户 / 2 万订阅 / 10 万支付 / 2 万退款 / 5 万工单 / 300 文档 / 5000 记忆 / 1000 评测用例。

```powershell
$env:PYTHONNOUSERSITE = "1"
$env:DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations"
& E:\anaconda3\envs\edu_agent\python.exe -m alembic upgrade head
& E:\anaconda3\envs\edu_agent\python.exe scripts/generate_synthetic_data.py --scale small --reset --seed 42
& E:\anaconda3\envs\edu_agent\python.exe scripts/verify_synthetic_data.py
```

说明：

- `--reset` 会 TRUNCATE 全部业务表后重建数据；`--seed` 固定随机种子保证可复现。
- 24 个注入场景（重复扣费、Prompt Injection、越权导出、审批过期、并发退款等）以独立会话消息方式写入，供端到端演示与评测使用。
- 生成的数据与测试隔离：`tests/unit/database` 的 fixture 会在结束时 `drop_all` 数据库表，因此请先跑测试再生成演示数据，或生成后再跑 `alembic upgrade head` 重建表。
- `scripts/verify_synthetic_data.py` 校验行数、同租户外键引用、跨租户隔离、唯一约束和领域状态值。

## Docker Compose 与部署

项目根目录 `docker-compose.yml` 提供完整本地部署：

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

启动后：

- 前端控制台：`http://localhost:3000/`
- 后端 API：`http://localhost:8000/`
- Mock 外部服务：`http://localhost:8001/`
- Prometheus：`http://localhost:19090/`
- Grafana：`http://localhost:13000/`
- PostgreSQL：`localhost:54329`
- Redis：`localhost:16380`
- Milvus：`localhost:19541`

首次启动需要执行数据库迁移：

```powershell
$env:PYTHONNOUSERSITE = "1"
$env:DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations"
& E:\anaconda3\envs\edu_agent\python.exe -m alembic upgrade head
```

GitHub Actions 流水线见 `.github/workflows/ci.yml`，会启动 PostgreSQL/Redis/Milvus/etcd/MinIO，执行迁移、完整测试和迁移漂移检查。

## Prometheus 与 Grafana

`docker compose up -d --build` 会同时启动 Prometheus 和 Grafana：

- Prometheus：`http://localhost:19090/`，抓取后端 `/metrics`；
- Grafana：`http://localhost:13000/`，默认账号由 `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` 控制，未设置时为 `admin` / `admin`。

`infra/prometheus/prometheus.yml` 定义后端抓取目标，`infra/grafana/provisioning/` 预置 Prometheus 数据源。当前 `/metrics` 提供 HTTP 请求计数和应用健康指标，业务级 Trace、成本、Agent 指标继续通过 Runtime API 查看。

## Kubernetes 与运维

`infra/kubernetes/` 提供 Namespace、ConfigMap、Secret 示例、后端/前端 Deployment、Service 和 Ingress。生产 Secret 应通过外部 Secret 管理注入，不应使用示例文件。数据库备份、恢复、密钥轮换和故障恢复流程见 [`docs/architecture/部署运维手册.md`](docs/architecture/部署运维手册.md)。

## Worker 与 Scheduler

项目使用 Redis 队列执行异步任务：

- `backend/tasks/worker.py`：消费 `ecop:tasks`，当前支持 `memory.expire`；
- `backend/tasks/scheduler.py`：定时入队 `memory.expire`，默认每 3600 秒；
- `memory.expire`：软删除已超过 TTL 的长期记忆记录。

Docker Compose 已包含 `backend-worker` 和 `backend-scheduler` 服务。本地单独启动：

```powershell
$env:PYTHONNOUSERSITE = "1"
$env:REDIS_URL = "redis://localhost:16380/0"
& E:\anaconda3\envs\edu_agent\python.exe -m backend.tasks.worker
& E:\anaconda3\envs\edu_agent\python.exe -m backend.tasks.scheduler
```

当前 Worker 只处理已实现的维护任务，后续可扩展知识重索引、评测执行和通知发送。

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
- `POST /api/v1/conversations`：创建客户会话并保存首条消息；
- `GET /api/v1/conversations`：按租户查看会话列表；
- `GET /api/v1/conversations/{conversation_id}`：查看会话与消息；
- `POST /api/v1/conversations/{conversation_id}/messages`：追加会话消息；
- `POST /api/v1/auth/tokens`：为当前租户活动用户签发本地 JWT Bearer Token；
- `GET /api/v1/evaluations`：查看当前租户评测运行；
- `POST /api/v1/evaluations/run`：运行检索评测并返回 Recall@K、MRR、NDCG；
- `GET /api/v1/runtime/traces`：查看当前租户 Runtime Trace；
- `GET /api/v1/runtime/traces/{trace_id}`：查看 Trace 和 Span 详情；
- `GET /api/v1/runtime/costs`：查看当前租户 Token 和成本汇总；
- `GET /api/v1/runtime/agents`：查看 Agent 定义清单；
- `POST /api/v1/tickets`：创建租户作用域工单；
- `GET /api/v1/tickets`：按租户查看工单列表；
- `GET /api/v1/tickets/{ticket_id}`：查看工单、消息、事件和审批关联；
- `PATCH /api/v1/tickets/{ticket_id}`：更新工单状态、优先级或追加内部备注；
- `GET /api/v1/approvals`：按租户查看审批列表；
- `GET /api/v1/approvals/{approval_request_id}`：查看审批详情与动作轨迹；
- `GET /api/v1/knowledge/search`：检索当前租户 active 知识文档；
- `POST /api/v1/knowledge/documents`：摄取知识文档、分片并写入 Milvus 向量索引；
- `GET /api/v1/knowledge/documents`：查看当前租户 active 文档；
- `DELETE /api/v1/knowledge/documents/{document_id}`：软删除文档并清理 Milvus 分片；
- `POST /api/v1/knowledge/reindex`：对当前租户 active 文档重建向量索引；
- `POST /api/v1/refunds`：提交本地退款申请；
- `POST /api/v1/approvals/{approval_request_id}`：批准或拒绝退款审批；
- `GET /api/v1/workflows/{thread_id}`：按租户查询脱敏工作流状态。
- `GET /metrics`：Prometheus 文本格式 HTTP 请求指标。

业务请求需要携带开发环境 Header：`X-Tenant-Id`、`X-Actor-Id`、`X-Actor-Type`，可选 `X-Request-Id`。这些 Header 只用于当前本地开发和集成测试，不等同于生产 JWT/OAuth 认证。客户咨询需要 `customer.consult`，会话读写需要 `conversation.create` / `conversation.read` / `conversation.write`，工单需要 `ticket.create` / `ticket.read` / `ticket.update`，审批查看需要 `approval.read`，知识库需要 `knowledge.search` / `knowledge.ingest` / `knowledge.delete`，退款接口需要 `refund.request` / `refund.approve`，评测需要 `evaluation.read` / `evaluation.run`，Runtime 查看需要 `runtime.read`。接口详细合同见 [`docs/superpowers/specs/2026-08-02-退款业务HTTP API设计.md`](docs/superpowers/specs/2026-08-02-退款业务HTTP%20API设计.md) 和 [`docs/superpowers/specs/2026-08-02-客户咨询API与模型网关工厂设计.md`](docs/superpowers/specs/2026-08-02-客户咨询API与模型网关工厂设计.md)。

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

## 生产级前端（Next.js）

`frontend/` 是 Next.js + TypeScript + Tailwind CSS v4 生产级前端，提供三个门户：

- **客户门户** `/portal`：提交问题（SSE 实时进度）、我的工单、处理记录
- **客服工作台** `/workspace`：工单队列、工单处理、审批（批准/拒绝走 Checkpoint 恢复）、知识检索、咨询调试
- **管理控制台** `/admin`：平台总览、Runtime Trace/成本/Agent、评测、知识库管理、会话活动

启动（需先启动后端与数据库，见上文）：

```powershell
cd frontend
npm install
npm run dev
```

访问 `http://localhost:3000/`，首次进入选择开发环境身份（租户 + 用户），请求通过 `next.config.ts` 的 rewrites 代理到 `http://localhost:8000`。认证沿用开发请求头边界（`X-Tenant-Id` / `X-Actor-Id` / `X-Actor-Type`），生产环境可切换 JWT。

```powershell
# 生产构建
cd frontend
npm run build
npm run start
```

旧静态控制台保留在 `frontend_legacy/`，仍由 FastAPI 在 `http://localhost:8000/` 提供，用于兼容验证；新前端独立运行于 3000 端口。

## 本地前端控制台（旧版）

FastAPI 会直接托管 `frontend_legacy/` 静态工作台，启动后端后访问：

```text
http://localhost:8000/
```

工作台提供总览、SSE 客户咨询、会话、工单、审批、知识库、Runtime 和评测八个视图：填写租户/用户 UUID 获取 JWT Token 后，可完成会话创建与消息追加、工单创建与状态更新、审批查看与决策、知识检索/摄取/归档/重建索引、客户咨询 SSE 进度事件，以及 Runtime Trace、成本和 Agent 清单。它仍是静态托管的企业级运营界面，不含生产级 Next.js 应用。

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

## Runtime 可观测 API

Runtime API 基于 PostgreSQL 中的 `runtime_traces`、`runtime_spans`、`tool_executions` 和 `agent_definitions` 返回当前租户可观测数据：

- Trace 列表和详情；
- Span 输入/输出摘要；
- Token 和成本汇总；
- Agent 定义清单。

当前返回数据库已持久化的脱敏摘要，不包含原始 Prompt、知识原文或敏感业务数据。

## Mock 外部服务

`mock_services/` 提供独立的模拟企业外部系统，用于本地开发、退款/工单闭环演示和测试：

- `POST /billing/refunds/preview`：退款预览；
- `POST /billing/refunds`：退款执行，按 `idempotency_key` 幂等；
- `GET /billing/refunds/{idempotency_key}`：退款状态；
- `GET /crm/customers/{customer_id}`：客户资料；
- `GET/POST /monitoring/incidents`：故障事件；
- `POST/GET /notification/notifications`：通知队列。

启动 Mock 服务：

```powershell
$env:PYTHONNOUSERSITE = "1"
& E:\anaconda3\envs\edu_agent\python.exe -m uvicorn mock_services.app:mock_services_app --port 8001
```

`MockBillingClient` 提供异步 HTTP 客户端，可被未来退款执行节点调用。当前核心退款仍以本地 PostgreSQL 状态为准，Mock 服务不会替代第三方支付网关。

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

本机已复制 BGE-M3 模型到项目本地目录，可直接使用：

```powershell
$env:BGE_M3_MODEL_PATH = "E:\ai\enterprise-customer-operations-platform\.worktrees\phase-2-domain-database\models\bge-m3"
```

真实模型验证脚本：

```powershell
$env:PYTHONNOUSERSITE = "1"
$env:MILVUS_URI = "http://localhost:19531"
& E:\anaconda3\envs\edu_agent\python.exe scripts/verify_bge_m3.py
```

本机已通过真实模型验证：BGE-M3 输出维度 1024，dense 向量 1024，稀疏向量 17 个词项权重，Milvus Dense + Sparse Hybrid Search 命中测试文档。

### Cross-Encoder 精排与检索评测

`scripts/evaluate_retrieval.py` 对多个租户的评测用例离线计算 Dense、Hybrid 融合与 Cross-Encoder 精排三路指标的 Recall@K、Precision@K、MRR、NDCG。真实 BGE Reranker 模型已下载到 `models/bge-reranker-base`（通过本地代理），通过 `RERANKER_MODEL_PATH` 指定：

```powershell
$env:PYTHONNOUSERSITE = "1"
$env:DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations"
$env:MILVUS_URI = "http://localhost:19531"
$env:BGE_M3_MODEL_PATH = "E:\ai\enterprise-customer-operations-platform\.worktrees\phase-2-domain-database\models\bge-m3"
$env:RERANKER_MODEL_PATH = "E:\ai\enterprise-customer-operations-platform\.worktrees\phase-2-domain-database\models\bge-reranker-base"
& E:\anaconda3\envs\edu_agent\python.exe scripts/evaluate_retrieval.py --tenant-ids <uuid1> <uuid2> ... --limit-cases 9
```

当前 5 个租户 45 个检索用例的实测结果：

| 指标 | Dense | Hybrid | Reranked |
| --- | --- | --- | --- |
| MRR | 0.8185 | 0.7926 | **0.8481** |
| NDCG@10 | 0.8644 | 0.8456 | **0.8876** |

Cross-Encoder 精排相对 RRF 融合 MRR +0.056、NDCG@10 +0.042，验证真实 BGE Reranker 已接入检索链路。

开启 BGE-M3 稀疏向量召回（集合名升级为 `ecop_knowledge_chunks_v2`）：

```powershell
$env:SPARSE_VECTOR_ENABLED = "1"
$env:MILVUS_COLLECTION = "ecop_knowledge_chunks_v2"
```

未配置 `BGE_M3_MODEL_PATH` 时，稀疏向量使用确定性本地哈希向量，不访问外网；配置后使用 FlagEmbedding BGE-M3 生成 sparse lexical weights，Milvus 使用 Dense + Sparse hybrid search。

精排默认使用确定性 RRF 得分排序；如需启用 Cross-Encoder，指定本地模型目录：

```powershell
$env:RERANKER_MODEL_PATH = "D:\models\BAAI\bge-reranker-large"
```

本阶段不保存原始知识正文到审计、日志或运行轨迹；搜索响应只返回文档摘要、RRF 得分和最多 300 字的分片摘要。BGE-M3 稀疏向量已提供可选适配器，真实模型加载和评测对比仍属于后续验证。

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
  --permissions refund.request refund.approve customer.consult conversation.create conversation.read conversation.write ticket.create ticket.read ticket.update approval.read knowledge.search knowledge.ingest knowledge.delete evaluation.read evaluation.run runtime.read
```

该脚本只允许声明的权限码，并且重复执行幂等；仅用于开发和测试，不替代生产认证、角色审批和密钥管理。

## 目录说明

- `backend/domain`：支付、退款、工单和审批状态机
- `backend/database/models`：身份、计费、工单、治理和评测模型
- `backend/database/repositories`：租户作用域 Repository
- `backend/database/unit_of_work.py`：事务边界与 Repository 组合
- `backend/rag`：Embedding、文本分片、Milvus 向量存储和知识摄取服务
- `backend/evaluation`：检索评测指标和评测 Runner
- `backend/memory`：确定性记忆提取、写入策略和候选记忆服务
- `backend/llm`：模型网关、结构化回复、安全过滤、模型路由、Prompt Registry 和上下文预算
- `mock_services`：Billing/CRM/Monitoring/Notification 模拟外部服务
- `frontend`：由 FastAPI 静态托管的本地演示控制台
- `alembic/versions`：数据库迁移链
- `scripts/verify_database.py`：数据库结构和迁移头验收
- `docs/architecture`：中文领域模型、数据库、事务、Guard、多智能体工作流和退款审批闭环文档
- `docs/superpowers/specs`：模型网关、Guard、退款业务和客户咨询 API 合同
- `docs/验证记录`：按实际 Python 环境和数据库容器生成的验收证据

## 约束

普通业务查询必须携带 `TenantScope`；金额使用 `Decimal` 和 `NUMERIC(18, 2)`；退款幂等键按租户隔离；敏感 payload 只保存脱敏摘要。计费 Agent 必须经过策略门禁，未知支付执行状态转人工处理。

退款链路的“完成”仅表示本地退款申请、`Refund`、审批动作、审计事件和运行 Checkpoint 已写入 PostgreSQL；当前不调用第三方支付网关，因此不代表第三方资金已经到账。详细时序见 [`docs/architecture/数据库驱动退款审批闭环.md`](docs/architecture/数据库驱动退款审批闭环.md)。
