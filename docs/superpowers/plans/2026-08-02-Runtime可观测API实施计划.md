# Runtime 可观测 API 实施计划

**Goal:** 为后续 Runtime Dashboard 提供 Trace、Span、Token/成本和 Agent 定义的可查询 API。

**Architecture:** `RuntimeRepository` 基于 `runtime_traces`、`runtime_spans` 和 `agent_definitions` 提供租户作用域查询；`backend/api/routes/runtime.py` 暴露 Trace 列表、Trace 详情、成本和 Agent 清单。

**Global Constraints:**

- 所有查询必须按租户过滤。
- 不返回原始 Prompt、知识原文或敏感业务数据。
- 当前只查询 PostgreSQL 已持久化的脱敏摘要。

## Task 1: Runtime Repository

- [x] 增加 Trace 列表和详情查询。
- [x] 增加 Span 列表查询。
- [x] 增加 Token/成本汇总和 Agent 清单。

## Task 2: Runtime API

- [x] 新增 Trace 列表和详情路由。
- [x] 新增成本汇总和 Agent 清单路由。
- [x] 增加 `runtime.read` 权限。

## Task 3: 测试与文档

- [x] 增加 Repository 和 API 集成测试。
- [x] 更新 README 和架构文档。
- [x] 增加验证记录。
