# Runtime 可观测 API 验证记录

## 1. 验证范围

本次验证覆盖：

- Trace 列表和详情；
- Span 输入/输出摘要；
- Token 和成本汇总；
- Agent 定义清单；
- `runtime.read` 权限；
- 跨租户清理。

## 2. 测试结果

配置 `MILVUS_URI` 并包含真实 Milvus 集成测试：

```text
287 passed
```

未配置 `MILVUS_URI` 的默认回归：

```text
286 passed, 1 skipped
```

## 3. 当前边界

当前 Runtime API 返回 PostgreSQL 中已持久化的脱敏摘要，不包含原始 Prompt、知识原文或敏感业务数据。Prometheus/Grafana、OpenTelemetry 和完整 Runtime Dashboard 仍属于后续阶段。
