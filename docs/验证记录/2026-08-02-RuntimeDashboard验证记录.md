# Runtime Dashboard 验证记录

## 1. 验证范围

本次验证覆盖本地控制台 Runtime Dashboard：

- Trace 查看；
- 成本查看；
- Agent 清单查看；
- 前端静态资源引用；
- 完整后端回归。

## 2. 测试结果

配置 Milvus：

```text
290 passed
```

未配置 Milvus：

```text
289 passed, 1 skipped
```

## 3. 当前边界

当前 Dashboard 是静态控制台的最小观测视图，不包含图表、筛选、详情页或生产级 Next.js 前端。
