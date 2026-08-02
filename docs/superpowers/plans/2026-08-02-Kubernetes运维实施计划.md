# Kubernetes 运维实施计划

**Goal:** 为生产部署提供最小 Kubernetes 清单和数据库备份、恢复、Secret 轮换及故障恢复手册。

**Architecture:** `infra/kubernetes/` 包含 Namespace、ConfigMap、Secret 示例、后端/前端 Deployment、Service 和 Ingress；`docs/architecture/部署运维手册.md` 记录运维流程。

**Global Constraints:**

- 不把真实 Secret 写入仓库。
- 数据库恢复后必须执行迁移和结构校验。
- K8s 清单是生产基础，仍需企业级 Secret 管理和监控接入。

## Task 1: Kubernetes 清单

- [x] Namespace、ConfigMap、Secret 示例。
- [x] 后端/前端 Deployment、Service、Ingress。
- [x] 健康检查与资源限制。

## Task 2: 运维手册

- [x] PostgreSQL 备份与恢复。
- [x] MinIO/Milvus 备份说明。
- [x] Secret 轮换和故障恢复 Runbook。

## Task 3: 文档与验收

- [x] 更新 README 和架构文档。
- [x] 验证 YAML 语法。
- [x] 增加验证记录。
