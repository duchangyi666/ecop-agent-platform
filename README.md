# 企业级客户运营平台

这是一个与现有项目完全独立的企业级智能客服与工单处理 Agent 平台。当前已完成领域模型、PostgreSQL 数据库、租户隔离、事务边界、Alembic 迁移基础，以及 Supervisor + 五个专属 Agent 的 LangGraph 多智能体工作流。

## 当前技术基线

- Python：以本机 `edu_agent` 环境实际版本为准
- SQLAlchemy：2.0.49
- Pydantic：2.12.5
- LangGraph：1.1.10
- PostgreSQL：项目专用 Docker 容器，映射端口 `54329`
- 数据库连接：`postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations`

## 启动数据库与验证

在项目根目录执行：

```powershell
docker compose -f infra/compose/docker-compose.db.yml up -d postgres
python -m alembic upgrade head
python scripts/verify_database.py
python -m pytest tests/unit tests/integration/database -q
```

验证多智能体工作流：

```powershell
$env:PYTHONNOUSERSITE = "1"
python -m pip check
python -m pytest tests/unit tests/integration/database tests/integration/agent -q
python -m compileall -q backend scripts
python -m alembic check
```

如需显式指定连接串：

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations"
```

## 目录说明

- `backend/domain`：支付、退款、工单和审批状态机
- `backend/database/models`：身份、计费、工单、治理和评测模型
- `backend/database/repositories`：租户作用域 Repository
- `backend/database/unit_of_work.py`：事务边界与 Repository 组合
- `alembic/versions`：数据库迁移链
- `scripts/verify_database.py`：数据库结构和迁移头验收
- `docs/architecture`：中文领域模型、数据库、事务和多智能体工作流设计文档

## 约束

普通业务查询必须携带 `TenantScope`；金额使用 `Decimal` 和 `NUMERIC(18, 2)`；退款幂等键按租户隔离；敏感 payload 只保存脱敏摘要。计费 Agent 必须经过策略门禁，未知支付执行状态转人工处理。
