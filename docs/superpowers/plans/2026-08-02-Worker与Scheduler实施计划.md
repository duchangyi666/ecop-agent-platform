# Worker 与 Scheduler 实施计划

**Goal:** 增加基于 Redis 的异步任务队列、Worker 和 Scheduler，并实现长期记忆过期清理任务。

**Architecture:** `RedisTaskBroker` 使用 `ecop:tasks` 队列，`TaskWorker` 按任务类型分发，`TaskScheduler` 定时入队 `memory.expire`。`memory.expire` 软删除超过 TTL 的记忆记录。

**Global Constraints:**

- Redis 不存储长期业务事实。
- Worker 不承担退款、审批或外部支付执行。
- 自动测试使用内存 Broker，不依赖真实 Redis。

## Task 1: Broker 与 Worker

- [x] 增加任务模型和 Redis/内存 Broker。
- [x] 增加 `TaskWorker` 和任务处理。
- [x] 增加 `run_worker_forever`。

## Task 2: 维护任务与 Scheduler

- [x] 实现 `expire_memory_records`。
- [x] 增加 `TaskScheduler` 定时入队。
- [x] 增加 `run_scheduler_forever`。

## Task 3: 部署与文档

- [x] Compose 增加 worker/scheduler 服务。
- [x] 更新 `.env.example` 和 README。
- [x] 增加测试和验证记录。
