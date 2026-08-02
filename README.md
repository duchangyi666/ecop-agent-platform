# 企业级客户运营平台

这是一个与现有项目完全独立的企业级智能客服与工单处理 Agent 平台。当前已完成领域模型、PostgreSQL 数据库、租户隔离、事务边界、Alembic 迁移，以及输入安全 Guard、业务范围 Guard、Supervisor + 五个专属 Agent 的 LangGraph 多智能体工作流。退款链路已具备数据库持久化申请、审批 Checkpoint 和审批恢复能力。

## 当前技术基线

- Python：以本机 `edu_agent` 环境实际版本为准
- SQLAlchemy：2.0.36
- Pydantic：2.11.4
- LangGraph：1.0.9
- PostgreSQL：项目专用 Docker 容器，映射端口 `54329`
- Alembic 当前迁移头：`005_refund_approval_checkpoint`
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
& E:\anaconda3\envs\edu_agent\python.exe -m pytest tests/unit tests/integration/database tests/integration/agent -q
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
- `POST /api/v1/refunds`：提交本地退款申请；
- `POST /api/v1/approvals/{approval_request_id}`：批准或拒绝退款审批；
- `GET /api/v1/workflows/{thread_id}`：按租户查询脱敏工作流状态。

业务请求需要携带开发环境 Header：`X-Tenant-Id`、`X-Actor-Id`、`X-Actor-Type`，可选 `X-Request-Id`。这些 Header 只用于当前本地开发和集成测试，不等同于生产 JWT/OAuth 认证。客户咨询需要 `customer.consult` 权限，退款接口需要 `refund.request` / `refund.approve`。接口详细合同见 [`docs/superpowers/specs/2026-08-02-退款业务HTTP API设计.md`](docs/superpowers/specs/2026-08-02-退款业务HTTP%20API设计.md) 和 [`docs/superpowers/specs/2026-08-02-客户咨询API与模型网关工厂设计.md`](docs/superpowers/specs/2026-08-02-客户咨询API与模型网关工厂设计.md)。

## Guard 与安全边界

请求进入主图后按固定顺序经过 `input_security_guard` 和 `domain_guard`，再进入 `normalize_request`、Supervisor、专属 Agent 和策略门禁：

- Prompt Injection、凭据/银行卡号、超长输入：返回 `blocked`，不重试、不调用业务工具；
- 绕过审批、租户隔离或未授权工具：返回 `human_handoff`，转人工安全审核；
- 真实生产资金、外部系统等越界请求：返回 `out_of_scope`；
- 无法判断业务场景：返回 `needs_clarification`，下一动作是 `ask_clarification`；
- 退款服务只有在安全状态为 `allow`、业务域为 `billing` 时才会读取 Payment 或执行 `billing.preview` / 退款申请；
- 工单服务只有在安全状态为 `allow`、业务域为 `ticket` 时才会执行 `ticket.create` / `ticket.update`。

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

当前阶段只完成模型网关、结构化回复和输出安全边界，尚未接入 RAG、Milvus、SSE、正式身份认证或第三方支付。模型不能直接执行数据库写入和业务工具。

为开发用户授予退款权限：

```powershell
$env:PYTHONNOUSERSITE = "1"
$env:DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations"
& E:\anaconda3\envs\edu_agent\python.exe scripts\seed_demo_identity.py `
  --tenant-id <租户UUID> `
  --user-id <用户UUID> `
  --permissions refund.request refund.approve customer.consult
```

该脚本只允许声明的三个权限码，并且重复执行幂等；仅用于开发和测试，不替代生产认证、角色审批和密钥管理。

## 目录说明

- `backend/domain`：支付、退款、工单和审批状态机
- `backend/database/models`：身份、计费、工单、治理和评测模型
- `backend/database/repositories`：租户作用域 Repository
- `backend/database/unit_of_work.py`：事务边界与 Repository 组合
- `alembic/versions`：数据库迁移链
- `scripts/verify_database.py`：数据库结构和迁移头验收
- `docs/architecture`：中文领域模型、数据库、事务、Guard、多智能体工作流和退款审批闭环文档
- `docs/superpowers/specs`：模型网关、Guard、退款业务和客户咨询 API 合同
- `docs/验证记录`：按实际 Python 环境和数据库容器生成的验收证据

## 约束

普通业务查询必须携带 `TenantScope`；金额使用 `Decimal` 和 `NUMERIC(18, 2)`；退款幂等键按租户隔离；敏感 payload 只保存脱敏摘要。计费 Agent 必须经过策略门禁，未知支付执行状态转人工处理。

退款链路的“完成”仅表示本地退款申请、`Refund`、审批动作、审计事件和运行 Checkpoint 已写入 PostgreSQL；当前不调用第三方支付网关，因此不代表第三方资金已经到账。详细时序见 [`docs/architecture/数据库驱动退款审批闭环.md`](docs/architecture/数据库驱动退款审批闭环.md)。
