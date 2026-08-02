# Worker 与 Scheduler 验证记录

## 1. 验证范围

本次验证覆盖：

- 内存 Broker 入队/出队；
- Worker 任务分发；
- Scheduler 定时入队；
- `memory.expire` 软删除过期记忆；
- Compose worker/scheduler 配置。

## 2. 测试结果

定向测试：

```text
4 passed
```

完整回归在提交前重新执行。

配置 Milvus：

```text
294 passed
```

未配置 Milvus：

```text
293 passed, 1 skipped
```

真实 Redis 入队/出队验证：通过。

## 3. 当前边界

当前 Worker 只处理 `memory.expire`，不承担退款、审批或外部支付执行。真实 Redis 集成在 Compose 启动后验证。
