# 企业级客户运营平台

这是一个与现有项目完全独立的企业级智能客服与工单处理 Agent 平台。当前已完成领域模型、PostgreSQL 数据库、租户隔离、事务边界、Alembic 迁移，以及 Supervisor + 五个专属 Agent 的 LangGraph 多智能体工作流。退款链路已具备数据库持久化申请、审批 Checkpoint 和审批恢复能力。

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
- `POST /api/v1/refunds`：提交本地退款申请；
- `POST /api/v1/approvals/{approval_request_id}`：批准或拒绝退款审批；
- `GET /api/v1/workflows/{thread_id}`：按租户查询脱敏工作流状态。

业务请求需要携带开发环境 Header：`X-Tenant-Id`、`X-Actor-Id`、`X-Actor-Type`，可选 `X-Request-Id`。这些 Header 只用于当前本地开发和集成测试，不等同于生产 JWT/OAuth 认证。接口的详细合同见 [`docs/superpowers/specs/2026-08-02-退款业务HTTP API设计.md`](docs/superpowers/specs/2026-08-02-退款业务HTTP%20API设计.md)。

为开发用户授予退款权限：

```powershell
$env:PYTHONNOUSERSITE = "1"
$env:DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations"
& E:\anaconda3\envs\edu_agent\python.exe scripts\seed_demo_identity.py `
  --tenant-id <租户UUID> `
  --user-id <用户UUID> `
  --permissions refund.request refund.approve
```

该脚本只允许声明的两个权限码，并且重复执行幂等；仅用于开发和测试，不替代生产认证、角色审批和密钥管理。

## 目录说明

- `backend/domain`：支付、退款、工单和审批状态机
- `backend/database/models`：身份、计费、工单、治理和评测模型
- `backend/database/repositories`：租户作用域 Repository
- `backend/database/unit_of_work.py`：事务边界与 Repository 组合
- `alembic/versions`：数据库迁移链
- `scripts/verify_database.py`：数据库结构和迁移头验收
- `docs/architecture`：中文领域模型、数据库、事务、多智能体工作流和退款审批闭环文档

## 约束

普通业务查询必须携带 `TenantScope`；金额使用 `Decimal` 和 `NUMERIC(18, 2)`；退款幂等键按租户隔离；敏感 payload 只保存脱敏摘要。计费 Agent 必须经过策略门禁，未知支付执行状态转人工处理。

退款链路的“完成”仅表示本地退款申请、`Refund`、审批动作、审计事件和运行 Checkpoint 已写入 PostgreSQL；当前不调用第三方支付网关，因此不代表第三方资金已经到账。详细时序见 [`docs/architecture/数据库驱动退款审批闭环.md`](docs/architecture/数据库驱动退款审批闭环.md)。
