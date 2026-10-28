# 金融客户运营与服务 Agent 平台

> 企业级智能客服与工单处理 **Agent 平台** —— 基于 LangGraph 的多智能体编排，内置安全 Guard、RAG 向量知识库、数据库驱动的退款审批闭环，以及生产级三门户前端。

这是一个与现有项目完全独立的企业级智能客服与工单处理 Agent 平台。当前已完成领域模型、PostgreSQL 数据库、租户隔离、事务边界、Alembic 迁移，以及输入安全 Guard、业务范围 Guard、Supervisor + 五个专属 Agent 的 LangGraph 多智能体工作流。退款链路已具备数据库持久化申请、审批 Checkpoint 和审批恢复能力。

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.117-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.0-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/langgraph)
[![Next.js](https://img.shields.io/badge/Next.js-15-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Milvus](https://img.shields.io/badge/Milvus-2.4-00A1EA?logo=milvus&logoColor=white)](https://milvus.io)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com)

面向企业客户的**智能客服 + 工单 + 退款审批**一体化平台：客户提出问题，多智能体工作流自动完成安全检查、意图路由、知识检索、业务工具执行（工单 / 退款预览 / 审批申请），并以流式方式返回有依据的回复；高风险操作（如退款）进入可追踪的审批闭环，全程留痕、可审计、可恢复。

---

## ✨ 功能特性

| 能力                     | 说明                                                         |
| ------------------------ | ------------------------------------------------------------ |
| 🧠 **多智能体客服工作流** | LangGraph 编排：安全 Guard → 知识检索 → Supervisor 路由 → 5 个专属 Agent（客服 / 计费 / 工单 / 审批 / 知识）→ 策略门禁 |
| 🛡️ **安全 Guard 边界**    | Prompt Injection、凭据 / 卡号、超长输入直接拦截；越权 / 绕过审批转人工；拒绝时绝不调用业务工具 |
| 📚 **RAG 向量知识库**     | Milvus 向量召回 + PostgreSQL 关键词检索 RRF 混合；可选 BGE-M3 稀疏向量与 Cross-Encoder 精排 |
| 💰 **退款审批闭环**       | 提交本地退款申请（`POST /api/v1/refunds`）→ 数据库持久化 → 审批 Checkpoint → 审批恢复；幂等键按租户隔离，全程留痕 |
| ⚡ **低延迟流式回复**     | SSE 实时推送进度事件 + 逐字流式生成；进程级连接复用、规则路由优先、关闭模型思考模式，首字仅约 1~2s |
| 🖥️ **三门户前端**         | Next.js 15 + TypeScript：客户门户（提问 / 我的工单）、客服工作台（工单 / 审批 / 知识库）、管理控制台（Runtime / 评测 / 知识管理 / 会话活动） |
| 🧪 **评测系统**           | 检索评测（Recall@K / MRR / NDCG）+ QA Correctness（LLM-as-Judge）+ 安全 Guard 离线评测 |
| 📊 **可观测**             | Runtime Trace / Token 成本 / Agent 清单 API + Prometheus / Grafana 指标 |
| 🧠 **长期记忆**           | 对话中提取稳定用户偏好（脱敏存储，拒绝低置信度 / 凭据内容）；响应中的 `memory_candidate_count` 只报告候选数量 |
| 🔐 **认证边界**           | 本地 JWT 签发 + 开发 Header 降级；`AUTH_MODE=jwt-only` 生产模式强制 Bearer |
| 🧩 **Mock 外部服务**      | Billing（`billing/refunds` 幂等退款预览 / 执行）、CRM、Monitoring、Notification 模拟企业外部系统 |

---

## 🧠 架构总览

一条客户消息在主图中的执行链路：

```text
用户消息
   │
   ▼
┌─────────────────────┐    ┌──────────────────────┐
│  input_security_guard │──▶│     domain_guard      │
│  (注入/凭据/超长拦截)   │    │   (业务范围识别)        │
└─────────────────────┘    └──────────────────────┘
                                    │ in_scope
                                    ▼
                          ┌──────────────────────┐
                          │   normalize / retrieve │  ← RAG：Milvus + PG 混合检索
                          └──────────────────────┘
                                    │
                                    ▼
                          ┌──────────────────────┐
                          │ Supervisor 意图路由    │  ← 规则优先，LLM 路由可选
                          └──────────────────────┘
                                    │
          ┌──────────┬───────────────┼───────────────┬──────────┐
          ▼          ▼               ▼               ▼          ▼
   ┌──────────┐ ┌──────────┐  ┌────────────┐  ┌──────────┐ ┌──────────┐
   │ 客服 Agent │ │ 计费 Agent │  │ 工单 Agent  │  │ 审批 Agent │ │ 知识 Agent │
   └──────────┘ └──────────┘  └────────────┘  └──────────┘ └──────────┘
          │                    │ 策略门禁 policy_gate（计费/退款必须过门禁）
          ▼                    ▼
   ┌──────────────────────────────────────────┐
   │  结构化安全回复（ResponseSafetyFilter）    │  ← SSE 流式返回
   └──────────────────────────────────────────┘
```

- **安全边界前置**：任何业务工具调用前必须通过 `input_security_guard`（输入安全 Guard）与 `domain_guard`（业务范围 Guard）；
- **退款门禁**：计费 Agent 只有安全状态 `allow` 且业务域 `billing` 时才执行退款预览 / 申请，并写入审批 Checkpoint；
- **租户隔离**：所有查询、写入、审计、运行时 Trace 均按 `TenantScope` 隔离；
- **脱敏原则**：日志 / 审计 / Checkpoint 只保存摘要与哈希，不落原始 Key、Prompt 或知识原文。

---

## 🚀 快速开始

### 方式一：Docker Compose（推荐）

```powershell
git clone https://github.com/duchangyi666/ecop-agent-platform.git
cd ecop-agent-platform

Copy-Item .env.example .env      # 按需填入 DEEPSEEK_API_KEY / JWT_SECRET
docker compose up -d --build     # 见根目录 docker-compose.yml，含前后端/Worker/监控栈
```

首次启动需执行数据库迁移（宿主机执行，`DATABASE_URL` 默认指向 `localhost:54329`）：

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations"
python -m alembic upgrade head
```


> 完整部署（Kubernetes、备份恢复、密钥轮换）见 [`docs/architecture/部署运维手册.md`](docs/architecture/部署运维手册.md)。

### 方式二：本地开发

**1. 启动基础设施**（PostgreSQL / Redis / Milvus）：

```powershell
docker compose up -d postgres redis
docker compose -f infra/compose/docker-compose.rag.yml up -d   # Milvus 栈（可选）
```

**2. 启动后端 API**：

```powershell
$env:PYTHONNOUSERSITE = "1"
$env:DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations"
# 可选：接入真实模型（不配置则使用离线 FakeModelGateway）
$env:DEEPSEEK_API_KEY = "<你的 DeepSeek Key>"
$env:DEEPSEEK_BASE_URL = "https://api.deepseek.com"
$env:DEEPSEEK_MODEL = "deepseek-v4-flash"

python -m alembic upgrade head
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

> 若 8000 端口被占用，可改用 `--port 8080` 并将前端代理 `BACKEND_URL` 指向 8080。

**3. 启动前端**：

```powershell
cd frontend
npm install
npm run dev          # 访问 http://localhost:3000/
```

> 旧版本地前端控制台（`frontend_legacy/`）仍由 FastAPI 静态托管，启动后端后访问 `http://localhost:8000/`，用于兼容验证。

---

## 🔑 演示账号

在 `AUTH_MODE=dev` 下创建 5 个演示身份（默认租户 `clouddesk-demo`，幂等可重复执行）：

```powershell
python scripts/seed_demo_accounts.py
```

| 身份       | 邮箱                      | 权限摘要 |
| ---------- | ------------------------- | -------- |
| 平台管理员 | `admin@clouddesk.demo`    | 全部 16 项权限 |
| 客服专员   | `agent@clouddesk.demo`    | 咨询、会话、工单、审批查看、知识检索 |
| 财务审核员 | `finance@clouddesk.demo`  | 咨询、会话查看、退款申请 / 审批、Runtime 查看 |
| 演示客户   | `customer@clouddesk.demo` | 咨询、会话、工单创建 / 查看、知识检索 |
| 访客       | `guest@clouddesk.demo`    | 仅知识检索 |

这些身份不设置密码。在开发身份选择器 `/identity` 中选择对应租户和用户，或用脚本输出的 `tenant_id` / `user_id` 调用开发 Token 接口；企业密码登录使用 `/login` 的 OIDC 流程。开发身份列表 API 仅在 `AUTH_MODE=dev` 可用，`oidc` 和 `jwt-only` 模式返回 404。权限复用 `backend/auth/permissions.py` 的角色矩阵，数据库以组合的 `demo_*` 权限角色存储。重复执行不增加用户或授权行，不会重新启用已停用 / 删除的身份；发现已有额外权限时会报错，建议改用新的 `--tenant-slug`，不会自动撤销既有授权。该脚本只初始化身份，业务样例数据需另行生成。

初始化同一租户下的小型完整样例（包含上述五种身份、客户关联、付款、工单和三份知识文档）：

```powershell
python scripts/seed_demo_scenario.py
```

默认使用 `clouddesk-demo`，也可用 `--tenant-slug` 指定独立演示租户。脚本输出身份和业务对象 ID；开发身份选择器选择该租户后即可操作这些对象。重复执行保留已有对象及其业务状态，知识内容未变时不新增版本；如需全新的演示流程，使用新的租户 slug。此入口仅在 `AUTH_MODE=dev` 可运行，知识写入 PostgreSQL，不访问模型或 Milvus；退款只验证本地申请与审批，不执行第三方资金操作。

前后端启动并准备上述数据后，可在 `frontend` 目录运行 `npm run test:chat-persistence`，用本机已安装的 Playwright Chromium 检查对话跨页面、刷新和身份切换；默认访问 `http://127.0.0.1:3000`，可通过 `SMOKE_BASE_URL` 和 `SMOKE_TENANT_SLUG` 覆盖。测试会在独立浏览器上下文中发送演示咨询并产生记录；后端未配置模型密钥时使用离线模型，否则会调用已配置的模型服务。该测试仅适用于演示环境，不代表生产验收。

`npm run test:identity-cache` 可在同一演示环境验证应用内切换身份时，上一身份的业务缓存与 Bearer Token 不会继续用于新身份。运行时会读取演示工单并发起开发 Token 请求；服务端鉴权和租户隔离仍是安全边界。

`npm run test:approval` 会使用 seed 输出的 `payment_id` 创建一条本地退款申请，通过浏览器完成财务审批，并检查访客被拒绝、重复审批被拒绝、审批记录和 Runtime 轨迹。执行前在 `frontend` 目录设置环境变量（将值替换为本次 seed 输出）：

```powershell
$env:SMOKE_PAYMENT_ID = '<seed 输出的 payment_id>'
npm run test:approval
```

审批超过有效期后不能再批准或拒绝；查询接口按当前时间将尚未处理的过期申请显示在“已过期”，这一展示状态不会自动更改数据库记录或恢复工作流。

也可运行 `npm run test:demo` 顺序执行聊天、身份隔离和审批三项浏览器检查。审批脚本限制通过本机地址访问，并会在演示数据库新增退款与审批记录；请使用隔离的开发演示环境和虚构数据。重复 seed 不会清除这些记录，需要全新状态时使用新的演示租户。该测试使用开发身份，不验证 OIDC 或真实支付。

在 Windows 上，前后端已启动、依赖和 Playwright Chromium 已安装后，也可以从仓库根目录用一个命令初始化样例并执行上述三项检查，无需手动复制付款 ID：

```powershell
$env:AUTH_MODE = 'dev'
$env:DATABASE_URL = 'postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations'
.\scripts\run_demo_smoke.ps1 -TenantSlug 'clouddesk-demo'
```

这里的数据库必须与正在运行的演示后端一致。使用 `-TenantSlug` 指定新的租户可获得独立样例；脚本不删除已有数据。非默认地址可通过 `-BaseUrl` 指定本机前端，非默认 Python 可通过 `-PythonExecutable` 指定。脚本会写入虚构演示数据，仍需确保后端未配置真实模型密钥以进行离线演示。

需要更大规模的独立合成数据时（生成器默认使用 `demo-ops` 租户前缀，不与上述样例混用）：

```powershell
python scripts/generate_synthetic_data.py --scale small --seed 42 --tenant-prefix demo-ops
python scripts/verify_synthetic_data.py   # 校验行数、外键、跨租户隔离、唯一约束
```

## 🤖 Worker 与异步任务

Redis 队列执行异步维护任务（模块 `backend.tasks.worker` / `backend.tasks.scheduler`）：

- `backend/tasks/worker.py`：消费 `ecop:tasks` 队列；
- `backend/tasks/scheduler.py`：定时入队，默认每 3600s；
- `memory.expire`：软删除超过 TTL 的长期记忆记录。

## 🔐 认证与模型网关

- **认证**：`AUTH_MODE` 支持 `dev` / `jwt-only` / `oidc`。
  - `dev`：本地 JWT + 开发 Header（`X-Tenant-Id` 等），可用 `/api/v1/auth/tokens` 自助签发；
  - `jwt-only`：只接受 `Authorization: Bearer <token>`，开发 Header 失效；
  - `oidc`：浏览器走标准 OIDC Authorization Code + PKCE，后端作为 BFF 交换 code 并校验 ID Token，再签发平台 JWT；开发 Header 与 `/auth/tokens` 均禁用。
  - 本地 OIDC 使用 Dex：`docker compose -f infra/compose/docker-compose.identity.yml up -d`，issuer 为 `http://localhost:8081/dex`，演示账号 `demo@clouddesk.local / Demo@123456`。
- **模型网关**：应用启动时经 `create_model_gateway()` 创建网关并放入 `app.state`——未配置 `DEEPSEEK_API_KEY` 时使用离线 `FakeModelGateway`（本地启动与自动测试不访问外网）；`DEEPSEEK_API_KEY` 只允许从运行时环境变量读取，仓库、测试、日志与文档不保存 Key、完整 Prompt 或模型响应原文；自动回归不执行真实 API 冒烟请求。
- **模型路由与 Prompt**：`MODEL_ROUTE_MODEL` / `MODEL_ROUTE_PROVIDER` 配置模型路由（默认 `deepseek-v4-flash`）；`PromptRegistry` 管理版本化 Prompt 模板；`ContextBudget` 对知识证据与系统 Prompt 做字符预算，防止上下文无限拼接。

`AUTH_MODE=oidc` 已在本地 Dex 上验证；生产需把 issuer/client 换为企业 IdP（Keycloak / Entra ID / Auth0），并把浏览器侧 JWT 存储升级为 HttpOnly Cookie + CSRF 防护。开发 Header 只用于本地和集成测试，不代表生产边界。客户咨询需要 `customer.consult`，知识摄取需要 `knowledge.ingest`，Runtime 查询需要 `runtime.read`；其余接口同样执行租户与权限校验。

**权限治理**：后端统一使用 `backend/auth/permissions.py` 的 `Permission` 常量；新增受保护路由必须挂 `require_permission(...)`，`tests/unit/api/test_route_permissions.py` 会扫描路由并拒绝缺失或未知权限。前端使用 `frontend/lib/permissions.ts` 与可复用 `<Can permission="...">` 门禁；它只负责 UX，安全边界始终在后端。

**浏览器与请求边界**：后端统一设置 CSP、X-Frame-Options、nosniff、Referrer Policy 与 Permissions Policy；HSTS 仅在 HTTPS 请求上启用。CORS 默认不开放跨域，如确需前后端跨域部署，使用逗号分隔的 `CORS_ALLOWED_ORIGINS=https://console.example.com` 显式配置；不接受 `*`、带路径或带账号信息的来源。POST/PUT/PATCH 请求体默认限制为 1 MiB，可通过 `MAX_REQUEST_BODY_BYTES` 调整；应用同时校验 `Content-Length` 和实际接收字节，超限返回 413。普通 HTTP 请求默认具有 120 秒处理截止时间，可通过 `REQUEST_TIMEOUT_SECONDS` 调整，超时返回结构化 504；SSE 客服流与 `/mcp/*` 长连接不受该截止时间影响，应由各自的会话和下游调用预算治理。

应用层默认按实际连接客户端 IP 执行每 60 秒 120 次请求的固定窗口限流，可通过 `RATE_LIMIT_REQUESTS`、`RATE_LIMIT_WINDOW_SECONDS` 和 `RATE_LIMIT_MAX_CLIENTS` 调整；超限返回结构化 429 以及 `Retry-After`、`RateLimit-*` 响应头。限流不信任客户端提供的 `X-Forwarded-For`，健康检查、就绪检查、指标抓取和 CORS 预检不计数。该内存限流仅提供单实例防滥用保护；多副本生产部署必须在可信反向代理/API Gateway 或共享 Redis 中统一解析真实来源并实施租户配额。

**租户隔离（RLS）**：Alembic `010` 为 35 张业务表启用 `tenant_isolation` policy，应用通过 `set_config('app.tenant_id', ..., true)` 在每个事务设置租户上下文。当前迁移使用 `ENABLE` 而非 `FORCE`，本地表 owner 仍会绕过策略；**生产必须使用非 owner 的 `app_rw` 角色**，否则 RLS 不会生效。CI/测试用 `pg_read_all_data` / `pg_write_all_data` 非 owner 角色验证跨租户读取和写入拒绝。身份表（`users`/`roles`/`permissions`/`user_roles`）暂不启用 RLS，登录由身份服务单独处理。

迁移 `011` 将事务结束后可能出现的空租户设置视为未设置：非 owner 角色读取不到租户业务行，写入被拒绝。集成测试使用单连接池验证提交和回滚后连接复用，以及租户切换；这不改变表 owner 绕过 RLS 的限制。

本地体验 RLS 强制模式：

```powershell
Get-Content infra\postgres\roles.sql -Raw | docker exec -i ecop-postgres-validation psql -U app -d enterprise_customer_operations
docker exec ecop-postgres-validation psql -U app -d enterprise_customer_operations -c "ALTER ROLE app_rw PASSWORD 'app_rw_dev_2026';"
$env:DATABASE_URL = "postgresql+asyncpg://app_rw:app_rw_dev_2026@localhost:54330/enterprise_customer_operations"
.\scripts\run_demo_backend.ps1
```

## 📈 可观测

- `GET /healthz`：进程存活；`GET /readyz`：数据库、Redis、Milvus 依赖检查（数据库不可用返回 503）。
- 每个请求返回 `X-Request-Id`，并写入结构化日志；`LOG_FORMAT=json` 可直接接入 Loki/ELK。
- `OTEL_ENABLED=1` 时启用 OpenTelemetry FastAPI / HTTPX / SQLAlchemy 自动埋点；`OTEL_EXPORTER_OTLP_ENDPOINT` 指向 Collector，未配置时默认不产生 exporter 网络请求。
- `GET /metrics` 保留 Prometheus 文本指标（请求数、耗时直方图、健康状态）。
- 本地监控栈：`docker compose -f infra/compose/docker-compose.monitoring.yml up -d`，Prometheus `http://localhost:19090`，Alertmanager `http://localhost:19093`，Jaeger `http://localhost:16686`，Grafana `http://localhost:13000`（admin/admin）。预置 `CloudDesk API Overview` 看板与 3 条告警规则（后端宕机、5xx、P95 延迟）。
- Trace 落库：后端设置 `OTEL_ENABLED=1`、`OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318` 后，Jaeger 中可查询 `clouddesk-api` 的 SERVER/HTTPX/SQLAlchemy span。

## 🔌 HTTP API 与流式事件

后端入口为 `backend.main:app`，主要接口包括：

- `POST /api/v1/customer-consultations`：执行安全 Guard、知识检索和多智能体咨询工作流；
- `POST /api/v1/customer-consultations/stream`：通过 SSE 返回 `started`、`evidence`、`completed` 和 `done` 事件，不输出思维链、系统 Prompt、Key 或知识原文；
- `POST /api/v1/conversations`、`GET /api/v1/conversations`：创建和查询租户会话；
- `POST /api/v1/tickets`、`GET /api/v1/tickets`：创建和查询工单；
- `POST /api/v1/refunds`、`POST /api/v1/approvals/{approval_request_id}`：提交本地退款申请并完成审批恢复；
- `POST /api/v1/knowledge/documents`、`GET /api/v1/knowledge/search`：知识摄取与检索；
- `POST /api/v1/evaluations/run`：运行检索评测并返回 Recall@K、MRR 与 NDCG；
- `GET /api/v1/runtime/traces`：查询当前租户的脱敏 Runtime Trace。

退款链路的“完成”只表示本地退款申请、审批动作、审计事件和 Checkpoint 已持久化，不代表第三方资金已经到账。

## 📚 RAG 向量知识库

- `POST /api/v1/knowledge/documents` 摄取知识 → 文本分片写入 `knowledge_chunks` → 同步 Milvus 向量集合
- `GET /api/v1/knowledge/search`：配置 `MILVUS_URI` 时使用向量召回 + PostgreSQL 关键词检索的 RRF 混合结果，未配置时降级为 PG 标题检索
- 默认使用确定性离线 Embedding（不下载模型、不访问外网）；启用 BGE-M3 稀疏向量：`SPARSE_VECTOR_ENABLED=1`（集合名 `ecop_knowledge_chunks_v2`），指定本地模型 `models\bge-m3`（可用 `scripts/verify_bge_m3.py` 验证输出维度）；启用 Cross-Encoder 精排：`RERANKER_MODEL_PATH`
- 客户咨询响应中的 `knowledge_evidence_count` 只报告命中数量，不返回知识原文

## 📚 文档

| 主题                 | 文档                                                         |
| -------------------- | ------------------------------------------------------------ |
| 领域模型与数据库设计 | [领域模型与数据库设计.md](docs/architecture/领域模型与数据库设计.md) |
| 多智能体工作流       | [多智能体LangGraph工作流.md](docs/architecture/多智能体LangGraph工作流.md) |
| 退款审批闭环         | [数据库驱动退款审批闭环.md](docs/architecture/数据库驱动退款审批闭环.md) |
| 状态机与事务边界     | [状态机与事务边界.md](docs/architecture/状态机与事务边界.md) · [工单工具与租户事务边界.md](docs/architecture/工单工具与租户事务边界.md) |
| RAG 与知识检索       | [知识检索工具与租户边界.md](docs/architecture/知识检索工具与租户边界.md) |
| 部署与运维           | [部署运维手册.md](docs/architecture/部署运维手册.md)         |
| API 设计合同         | [客户咨询 API](docs/superpowers/specs/2026-08-02-客户咨询API与模型网关工厂设计.md) · [退款业务 API](docs/superpowers/specs/2026-08-02-退款业务HTTP%20API设计.md) · [模型网关与安全设计](docs/superpowers/specs/2026-08-02-模型网关与结构化回复安全设计.md) |

---

## 🧪 测试与 CI

GitHub Actions 流水线（`.github/workflows/ci.yml`）会自动启动 PostgreSQL / Redis / Milvus / etcd / MinIO，执行迁移、完整测试与迁移漂移检查。

```powershell
# 单元测试 + 集成测试（需要本地基础设施）
$env:TEST_DATABASE_URL = $env:DATABASE_URL   # 必须显式指定，测试不会回退到 DATABASE_URL
.\.venv\Scripts\python.exe -m pytest tests/unit tests/integration/database tests/integration/agent tests/integration/api tests/integration/vectorstore tests/integration/external_services -q

# 数据库结构与迁移头验收
.\.venv\Scripts\python.exe scripts/verify_database.py
.\.venv\Scripts\python.exe -m alembic check
```

关键测试覆盖：Guard 拦截、业务域识别、退款策略、审批恢复、知识摄取与检索、SSE 流式、权限矩阵、API 合同（README 与代码一致性）。

---

## ⚙️ 技术栈

| 层     | 技术                                                         |
| ------ | ------------------------------------------------------------ |
| 后端   | Python 3.11 · FastAPI · SQLAlchemy 2.0（asyncpg）· Pydantic 2 · LangGraph 1.0 · Alembic |
| LLM    | DeepSeek（OpenAI-compatible）· provider-neutral `ModelGateway` 抽象 · 离线 `FakeModelGateway` 降级 |
| 存储   | PostgreSQL · Redis（Worker 队列）· Milvus（向量检索，可降级） |
| RAG    | 确定性离线 Embedding（可选 BGE-M3）· RRF 混合检索 · Cross-Encoder 精排（可选） |
| 前端   | Next.js 15 · TypeScript · Tailwind CSS v4 · Zustand · TanStack Query |
| 可观测 | Runtime Trace / Cost API · Prometheus · Grafana              |
| 部署   | Docker Compose · Kubernetes（`infra/kubernetes/`）· GitHub Actions |

---

## 🔬 评测结果

5 个租户 45 个检索用例的离线实测（`scripts/evaluate_retrieval.py`）：

| 指标    | Dense  | Hybrid (RRF) | Reranked (BGE) |
| ------- | ------ | ------------ | -------------- |
| MRR     | 0.8185 | 0.7926       | **0.8481**     |
| NDCG@10 | 0.8644 | 0.8456       | **0.8876**     |

Cross-Encoder 精排相对 RRF 融合 **MRR +0.056、NDCG@10 +0.042**，验证真实 BGE Reranker 已接入检索链路。

---

## 🗂️ 项目结构

```text
backend/
├── agent/                 # LangGraph 多智能体：Guard、Supervisor、领域 Agent、策略门禁
├── api/routes/            # FastAPI 路由（咨询 / 会话 / 工单 / 审批 / 退款 / 知识库 / 评测 / Runtime / 认证）
├── auth/                  # JWT 签发 / 校验、密码哈希、认证模式
├── database/              # 模型、迁移、租户作用域 Repository、UnitOfWork 事务边界
├── llm/                   # 模型网关（DeepSeek / Fake）、结构化回复、安全过滤、Prompt Registry、上下文预算
├── rag/                   # Embedding、分片、Milvus 向量存储、混合检索、知识摄取
├── memory/                # 确定性记忆提取与写入策略
├── evaluation/            # 检索 / QA / Guard 评测
└── observability/         # Prometheus 指标
frontend/                  # Next.js 三门户（客户门户 / 客服工作台 / 管理控制台）
frontend_legacy/           # FastAPI 静态托管的旧版控制台
mock_services/             # Billing / CRM / Monitoring / Notification 模拟外部服务
infra/                     # docker-compose、Kubernetes、Prometheus、Grafana
scripts/                   # 演示数据生成、账号 seed、检索评测、数据库验收
docs/                      # 架构文档与 API 设计合同
tests/                     # 单元 / 集成测试（unit · integration/database · api · agent · vectorstore）
```
