# Claude 继续开发交接说明

## 1. 你接手的项目

这是一个完全独立的新项目：

```text
E:\ai\enterprise-customer-operations-platform
```

本次交接应继续使用已经完成工作的独立工作树和分支：

```text
工作树：E:\ai\enterprise-customer-operations-platform\.worktrees\phase-2-domain-database
分支：phase-2-domain-database
当前提交：28a1532
```

注意：主工作树当前仍在 `master` 分支，提交为 `ceaeb53`，不包含本次模型网关和客服子图实现。不要直接在主工作树上继续，也不要擅自合并分支。

用户明确要求：

- 项目必须与 EduAgent、EduRAG 和其他现有项目完全分开；
- 后续新增文档使用中文文件名；
- Python、依赖和工具版本以实际项目环境为准，不能凭空升级或降级；
- 不创建子 agent，所有后续工作在当前分支完成；
- 不使用、保存、回显用户曾在对话中暴露的 DeepSeek Key；该 Key 必须先撤销并重新生成。

## 2. 当前已经完成的内容

### 基础平台

- 企业客户运营平台独立目录、PostgreSQL、Alembic、租户隔离和 Unit of Work；
- 领域模型：客户、支付、退款、工单、审批、治理、运行时追踪和 Checkpoint；
- Input Security Guard、Domain Guard、Supervisor 和客服/知识/计费/工单/审批五个专属 Agent 子图；
- 退款申请、审批、幂等、审计、租户隔离和数据库集成测试。

### 本阶段新增的模型能力

- `backend/llm/config.py`：运行时环境变量配置，Key 使用 `SecretStr`；
- `backend/llm/contracts.py`：`ResponseDraft`、`ModelUsage`、`ModelCallError`；
- `backend/llm/gateway.py`：provider-neutral `ModelGateway` Protocol；
- `backend/llm/deepseek.py`：基于 `httpx==0.28.1` 的 OpenAI-compatible DeepSeek HTTP 适配器；
- `backend/llm/fake.py`：离线 Fake Gateway；
- `backend/llm/safety.py`：敏感信息、内部信息和无证据业务承诺的确定性回复过滤器；
- `backend/agent/agents/customer_service.py`：`customer_service_model -> response_safety_filter` 客服子图；
- `backend/agent/graphs/main_graph.py`：支持注入 `ModelGateway`；
- 默认不传 Gateway 时使用固定 Fake Gateway，不读取环境变量、不访问网络。

模型只生成结构化回复草稿，不能直接执行数据库写入、退款、审批、工单或其他业务工具。回复草稿和最终回复只在本次图运行状态中传递，不能写入日志、审计错误或持久化敏感原文。

## 3. 已验证结果

验证必须使用项目环境：

```powershell
$env:PYTHONNOUSERSITE = "1"
& E:\anaconda3\envs\edu_agent\python.exe --version
```

实际环境版本：

```text
Python 3.11.15
httpx 0.28.1
pydantic 2.11.4
langgraph 1.0.9
langchain-core 1.2.16
SQLAlchemy 2.0.36
FastAPI 0.117.1
Alembic 1.18.5
pytest 8.3.4
pytest-asyncio 0.24.0
```

最近一次完整验证：

```text
199 passed
pip check: No broken requirements found.
compileall: 通过
alembic check: No new upgrade operations detected.
数据库结构验收: status=passed, missing_constraints=[]
疑似密钥扫描: 0
```

验证记录见：

```text
docs\验证记录\2026-08-02-模型网关与结构化回复安全验证记录.md
```

## 4. Claude 接手后的第一步

不要马上改代码。先执行并阅读：

```powershell
Set-Location E:\ai\enterprise-customer-operations-platform\.worktrees\phase-2-domain-database
git status --short
git log -5 --oneline
Get-Content README.md
Get-Content docs\architecture\多智能体LangGraph工作流.md
Get-Content docs\验证记录\2026-08-02-模型网关与结构化回复安全验证记录.md
Get-Content docs\superpowers\plans\2026-08-02-模型网关与结构化回复安全实施计划.md
$env:PYTHONNOUSERSITE = "1"
& E:\anaconda3\envs\edu_agent\python.exe -m pytest tests\unit tests\integration\database tests\integration\agent tests\integration\api -q
```

确认基线仍然通过后，再开始下一阶段。不要把计划文档中可能过时的文件名、节点名或版本号当成事实，必须以当前仓库实际代码和实际环境为准。

## 5. 推荐的下一阶段顺序

### 第一步：把模型网关接到应用运行时边界

当前模型网关已经可以被 `build_main_graph(model_gateway=...)` 注入，但 HTTP 应用还没有完整的客户咨询入口。下一步建议：

1. 增加应用级 Model Gateway Factory；
2. 默认使用 Fake Gateway，只有显式配置 `DEEPSEEK_API_KEY` 时才创建 `DeepSeekGateway`；
3. Key 只存在运行时配置，不进入 AgentState、日志、数据库或错误消息；
4. 为 Factory 和应用启动路径增加 Fake/未配置/DeepSeek 配置测试；
5. 不进行真实 API 自动测试。

### 第二步：增加客户咨询应用服务和 API 合同

在现有租户 Header、权限和审计边界上增加客户咨询入口，建议先完成：

- 请求模型、响应模型和租户作用域；
- 调用主图并返回 `final_response`、`next_action`、安全审查结果摘要；
- 模型异常统一转人工，不把供应商原文返回给客户端；
- API 集成测试只使用 Fake Gateway；
- 如要增加 SSE，先单独设计流式状态和脱敏规则，不要直接把模型原始流转发给客户端。

### 第三步：再扩展知识库、工单和工具调用

RAG、Milvus、SSE、正式 JWT/OAuth 和第三方支付目前都没有接入。新增前必须分别确认实际可用版本、数据来源、租户隔离和安全边界。不要为了“看起来完整”直接添加未验证的依赖或外部服务。

## 6. 必须遵守的安全规则

- 不要在任何命令、代码、测试、文档、日志或提交中写入真实 API Key；
- 不要调用用户在对话中暴露的旧 Key；
- 不要执行真实 DeepSeek API 冒烟请求，除非用户已经明确说明旧 Key 已撤销、新 Key 已生成，并再次明确要求执行；
- 自动测试使用 `FakeModelGateway` 或 `httpx.MockTransport`；
- 不要把完整 Prompt、思维链、供应商原始响应和 Authorization Header 写入状态持久化、日志或审计；
- 不要让模型直接决定退款、审批通过、支付成功或工单执行；
- 不要使用 `docker compose down -v`，不要清理数据库卷、表或迁移；
- 不要擅自合并到 `master`、推送远程或删除当前工作树；
- 每完成一个阶段，先运行测试、`pip check`、`compileall` 和 `git diff --check`，再报告结果。

## 7. 推荐的提交前命令

```powershell
Set-Location E:\ai\enterprise-customer-operations-platform\.worktrees\phase-2-domain-database
$env:PYTHONNOUSERSITE = "1"
& E:\anaconda3\envs\edu_agent\python.exe -m pytest tests\unit tests\integration\database tests\integration\agent tests\integration\api -q
& E:\anaconda3\envs\edu_agent\python.exe -m pip check
& E:\anaconda3\envs\edu_agent\python.exe -m compileall -q backend tests scripts
& E:\anaconda3\envs\edu_agent\python.exe -m alembic check
git diff --check
git status --short
```

## 8. 交接结论

请把 `phase-2-domain-database` 视为当前真实开发基线，从这里继续，不要从 `master` 重新开始。先完成“应用运行时 Gateway Factory”和“客户咨询 API 合同”，继续使用 Fake Gateway 做离线验证，再根据用户确认逐步扩展 RAG、工单工具和流式输出。
