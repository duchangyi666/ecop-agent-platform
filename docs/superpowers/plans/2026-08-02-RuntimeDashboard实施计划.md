# Runtime Dashboard 实施计划

**Goal:** 在本地静态控制台中接入 Runtime API，形成最小可用的 Trace、成本和 Agent 观测界面。

**Architecture:** `frontend/app.js` 新增 Runtime 按钮，调用 `/api/v1/runtime/traces`、`/api/v1/runtime/costs` 和 `/api/v1/runtime/agents`，展示脱敏 JSON 摘要。

**Global Constraints:**

- 页面只显示当前租户脱敏数据。
- 不显示原始 Prompt、知识原文或敏感业务数据。
- 当前为静态控制台 Dashboard，不是生产级 Next.js。

## Task 1: 页面与交互

- [x] 增加 Runtime 观测面板。
- [x] 接入 Trace、成本和 Agent API。
- [x] 显示统一脱敏 JSON 摘要。

## Task 2: 测试与文档

- [x] 前端资源测试覆盖 Runtime 接口。
- [x] 更新 README 和架构文档。
- [x] 增加验证记录。
