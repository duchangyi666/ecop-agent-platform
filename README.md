# 金融客户运营与服务 Agent 平台

> 企业级智能客服与工单处理 **Agent 平台** —— 基于 LangGraph 的多智能体编排，内置安全 Guard、RAG 向量知识库、数据库驱动的退款审批闭环，以及生产级三门户前端。

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

启动后访问：

| 服务                            | 地址                                                  |
| ------------------------------- | ----------------------------------------------------- |
| 前端控制台（Next.js 三门户）    | <http://localhost:3000/>                              |
| 后端 API / 旧版静态控制台       | <http://localhost:8000/>                              |
| Mock 外部服务（Billing/CRM 等） | <http://localhost:8001/>                              |
| Prometheus / Grafana            | <http://localhost:19090/> · <http://localhost:13000/> |
| PostgreSQL / Redis / Milvus     | `54329` · `16380` · `19541`                           |

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

一键创建 5 个演示账号（含租户、角色权限，幂等可重复执行）：

```powershell
python scripts/seed_demo_accounts.py
```

| 角色       | 邮箱                      | 密码              | 权限                                  |
| ---------- | ------------------------- | ----------------- | ------------------------------------- |
| 平台管理员 | `admin@clouddesk.demo`    | `Admin@123456`    | 全权限（含退款审批 / 评测 / Runtime） |
| 客服专员   | `agent@clouddesk.demo`    | `Agent@123456`    | 咨询 / 会话 / 工单 / 知识库           |
| 财务审核员 | `finance@clouddesk.demo`  | `Finance@123456`  | 退款申请 + 审批 / 审批查看            |
| 演示客户   | `customer@clouddesk.demo` | `Customer@123456` | 咨询 / 会话 / 工单 / 知识检索         |
| 访客       | `guest@clouddesk.demo`    | `Guest@123456`    | 最小只读权限                          |

生成业务演示数据（工单 / 审批 / 知识文档 / 会话，落库到指定租户）：

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

- **认证**：本地 JWT（`JWT_SECRET` 需 ≥32 字节，`JWT_TOKEN_EXPIRES_MINUTES` 控制有效期）；业务请求可带 `Authorization: Bearer <token>`，开发环境可降级到 `X-Tenant-Id` 等请求头；生产 `AUTH_MODE=jwt-only` 强制 Bearer 并禁用自助签发接口。
- **模型网关**：应用启动时经 `create_model_gateway()` 创建网关并放入 `app.state`——未配置 `DEEPSEEK_API_KEY` 时使用离线 `FakeModelGateway`（本地启动与自动测试不访问外网）；`DEEPSEEK_API_KEY` 只允许从运行时环境变量读取，仓库、测试、日志与文档不保存 Key、完整 Prompt 或模型响应原文；自动回归不执行真实 API 冒烟请求。
- **模型路由与 Prompt**：`MODEL_ROUTE_MODEL` / `MODEL_ROUTE_PROVIDER` 配置模型路由（默认 `deepseek-v4-flash`）；`PromptRegistry` 管理版本化 Prompt 模板；`ContextBudget` 对知识证据与系统 Prompt 做字符预算，防止上下文无限拼接。

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
pytest tests/unit tests/integration/database tests/integration/agent tests/integration/api tests/integration/vectorstore tests/integration/external_services -q

# 数据库结构与迁移头验收
python scripts/verify_database.py
python -m alembic check
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
