# 多智能体 LangGraph 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有独立企业客户运营平台上实现 LangGraph Supervisor + 专业 Agent 子图的多智能体工作流，并完成退款/计费异常的真实业务闭环。

**Architecture:** 使用 LangGraph 1.0.9 的 `StateGraph` 编排主图和专业子图。Supervisor 只负责结构化路由，专业 Agent 只负责领域推理，确定性策略和注册工具负责权限、金额、状态、租户和副作用控制。

**Tech Stack:** Python 3.11.15、LangGraph 1.0.9、LangChain Core 1.2.16、LangGraph Checkpoint 2.1.2、SQLAlchemy 2.0.36、Pydantic 2.11.4、PostgreSQL 15、pytest 8.3.4。

## Global Constraints

- 使用隔离环境 `E:\anaconda3\envs\edu_agent\python.exe`，设置 `PYTHONNOUSERSITE=1`。
- LangGraph 以当前实际安装版本 `1.0.9` 为准，不降级依赖。
- 业务数据继续使用现有 Repository、`TenantScope` 和 `UnitOfWork`，Agent 不直接操作数据库。
- 所有自定义文档使用中文文件名；标准 `README.md`、`pyproject.toml` 和 Python 文件名保持生态约定。
- 所有测试先写失败测试并确认失败，再实现最小代码。
- 不使用 `docker compose down -v`，数据库使用项目专用 PostgreSQL 54329。
- 多 Agent 之间使用结构化消息和受控枚举，不使用自然语言作为控制协议。

---

### Task 1: 固定多 Agent State、消息和工具契约

**Files:**
- Create: `backend/agent/__init__.py`
- Create: `backend/agent/contracts.py`
- Create: `backend/agent/state.py`
- Create: `tests/unit/agent/test_contracts.py`
- Create: `tests/unit/agent/helpers.py`
- Modify: `pyproject.toml`

**Interfaces:**
- `AgentState`：主图共享状态。
- `AgentMessage`：Agent 间结构化消息。
- `SupervisorDecision`：Supervisor 路由结果。
- `SpecialistResult`：专业 Agent 输出。
- `ToolContract`：专业 Agent 可调用工具协议。

- [ ] **Step 1: 写失败测试**

```python
def test_supervisor_decision_rejects_unregistered_route():
    with pytest.raises(ValueError, match="unsupported route"):
        SupervisorDecision(route="route_unknown", reason="bad")


def test_agent_state_carries_tenant_scope_and_request_id():
    state = create_agent_state(scope=scope, request_id=request_id, message="refund")
    assert state.tenant_scope == scope
    assert state.request_id == request_id
    assert state.conversation[0].content == "refund"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/unit/agent/test_contracts.py -q`

Expected: FAIL because the agent package and contracts do not exist。

- [ ] **Step 3: 加入实际 LangGraph 依赖并实现契约**

在 `pyproject.toml` 增加 `langgraph==1.0.9`；在 `state.py` 中定义 `AgentState` 和 `create_agent_state(...)` 工厂，在 `contracts.py` 中定义 `SupervisorDecision`、`SpecialistResult`、`AgentMessage` 和 `ToolContract`。测试辅助函数 `scope`、`request_id` 和 `state_for_*` 统一放在 `tests/unit/agent/helpers.py`。路由只允许 `route_customer`、`route_knowledge`、`route_billing`、`route_ticket`、`route_approval`、`ask_clarification`、`human_handoff`、`finish`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/unit/agent/test_contracts.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml backend/agent tests/unit/agent
git commit -m "feat: define multi-agent state and contracts"
```

### Task 2: 实现 LangGraph 主图和 Supervisor 路由

**Files:**
- Create: `backend/agent/graphs/main_graph.py`
- Create: `backend/agent/agents/supervisor.py`
- Create: `backend/agent/nodes/normalize.py`
- Create: `backend/agent/nodes/routing.py`
- Create: `tests/unit/agent/test_supervisor_graph.py`

**Interfaces:**
- `build_main_graph() -> StateGraph`
- `supervisor_node(state: AgentState) -> dict[str, object]`
- `route_from_supervisor(state: AgentState) -> str`

- [ ] **Step 1: 写失败测试**

```python
def test_supervisor_routes_refund_request_to_billing_agent():
    graph = build_main_graph().compile()
    result = graph.invoke(new_state("我要申请退款"))
    assert result["supervisor_decision"].route == "route_billing"


def test_supervisor_cannot_route_to_unregistered_agent():
    with pytest.raises(ValueError, match="unsupported route"):
        route_from_supervisor(state_with_route("route_unknown"))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/unit/agent/test_supervisor_graph.py -q`

Expected: FAIL because the LangGraph main graph is not implemented。

- [ ] **Step 3: 实现主图和 Supervisor**

使用 `StateGraph(AgentState)` 添加 `normalize_request`、`supervisor_agent` 和条件路由；Supervisor 先使用可替换的结构化决策器，不能直接执行工具；未知路由立即变成 `human_handoff`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/unit/agent/test_supervisor_graph.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/agent/graphs backend/agent/agents backend/agent/nodes tests/unit/agent/test_supervisor_graph.py
git commit -m "feat: add langgraph supervisor routing"
```

### Task 3: 实现专业 Agent 子图和 Agent 注册表

**Files:**
- Create: `backend/agent/agents/customer_service.py`
- Create: `backend/agent/agents/knowledge.py`
- Create: `backend/agent/agents/billing.py`
- Create: `backend/agent/agents/ticket.py`
- Create: `backend/agent/agents/approval.py`
- Create: `backend/agent/registry.py`
- Create: `tests/unit/agent/test_specialist_agents.py`

**Interfaces:**
- `build_customer_service_graph()`、`build_knowledge_graph()`、`build_billing_graph()`、`build_ticket_graph()`、`build_approval_graph()`。
- `AgentRegistry.register(name, graph, allowed_tools)`。
- `AgentRegistry.get(name)`。

- [ ] **Step 1: 写失败测试**

```python
def test_registry_exposes_five_specialist_agents():
    registry = build_default_registry()
    assert set(registry.names()) == {"customer_service", "knowledge", "billing", "ticket", "approval"}


def test_billing_agent_returns_structured_specialist_result():
    result = billing_agent_graph.invoke(state_for_billing())
    assert result["specialist_result"].agent_name == "billing"
    assert result["specialist_result"].status == "needs_policy_gate"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/unit/agent/test_specialist_agents.py -q`

Expected: FAIL because specialist subgraphs and registry do not exist。

- [ ] **Step 3: 实现五个专业子图**

每个 Agent 子图使用 LangGraph `StateGraph`；子图只返回 `SpecialistResult`，不直接写数据库。计费 Agent 只产出账单上下文和退款预览请求，工单和审批 Agent 只产出结构化业务意图。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/unit/agent/test_specialist_agents.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/agent/agents backend/agent/registry.py tests/unit/agent/test_specialist_agents.py
git commit -m "feat: add specialist agent subgraphs"
```

### Task 4: 接入工具注册表、策略门和退款业务闭环

**Files:**
- Create: `backend/agent/tools/base.py`
- Create: `backend/agent/tools/billing.py`
- Create: `backend/agent/policies/risk.py`
- Modify: `backend/agent/graphs/main_graph.py`
- Create: `tests/unit/agent/test_billing_tool_policy.py`
- Create: `tests/integration/agent/test_refund_workflow.py`

**Interfaces:**
- `ToolRegistry.register(tool)`、`ToolRegistry.for_agent(agent_name)`。
- `BillingTool.preview(request)`、`BillingTool.execute(request)`。
- `evaluate_refund_policy(context) -> PolicyDecision`。

- [ ] **Step 1: 写失败测试**

```python
def test_high_risk_refund_requires_approval():
    decision = evaluate_refund_policy(refund_context(amount=Decimal("5000.00")))
    assert decision.requires_approval is True


def test_billing_agent_cannot_access_ticket_tool():
    registry = build_default_tool_registry()
    assert registry.for_agent("billing").names() == ["billing.preview", "billing.execute"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/unit/agent/test_billing_tool_policy.py -q`

Expected: FAIL because tool registry and refund policy do not exist。

- [ ] **Step 3: 实现最小工具与策略门**

复用 Phase 2 的 `BillingRepository`、`SupportRepository` 和 `UnitOfWork`；preview 只读并生成幂等键，execute 只接受低风险或已审批动作。所有查询使用 `TenantScope`，未知执行状态禁止自动重试。

- [ ] **Step 4: 运行单元与集成测试**

Run: `python -m pytest tests/unit/agent/test_billing_tool_policy.py tests/integration/agent/test_refund_workflow.py -q`

Expected: PASS；低风险可执行、高风险进入审批、跨租户支付不可见、重复幂等键不产生第二条退款。

- [ ] **Step 5: 提交**

```bash
git add backend/agent/tools backend/agent/policies backend/agent/graphs tests/unit/agent tests/integration/agent
git commit -m "feat: add multi-agent billing tool policy flow"
```

### Task 5: 接入 Checkpoint、审批恢复、审计和运行追踪

**Files:**
- Create: `backend/agent/checkpoint.py`
- Create: `backend/agent/runtime.py`
- Modify: `backend/agent/graphs/main_graph.py`
- Create: `tests/unit/agent/test_checkpoint_runtime.py`
- Create: `tests/integration/agent/test_approval_resume.py`

**Interfaces:**
- `CheckpointStore.save(thread_id, state)`、`CheckpointStore.load(thread_id)`。
- `run_agent_workflow(request, checkpointer, registry)`。
- `persist_agent_runtime(state, node_name, result)`。

- [ ] **Step 1: 写失败测试**

```python
async def test_approval_interrupt_can_resume_with_same_idempotency_key(checkpoint_store):
    paused = await run_until_approval(refund_request())
    await checkpoint_store.save(paused.thread_id, paused.state)
    resumed = await resume_after_approval(paused.thread_id, approved=True)
    assert resumed.refund_idempotency_key == paused.refund_idempotency_key
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/unit/agent/test_checkpoint_runtime.py -q`

Expected: FAIL because CheckpointStore and resume flow do not exist。

- [ ] **Step 3: 实现 Checkpoint 与运行追踪**

先实现内存 CheckpointStore 供单元测试，再实现 PostgreSQL 持久化适配；使用现有 `RuntimeTrace`、`RuntimeSpan`、`ToolExecution` 和 `AuditLog` Repository/模型保存脱敏摘要。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/unit/agent/test_checkpoint_runtime.py tests/integration/agent/test_approval_resume.py -q`

Expected: PASS；审批恢复重新读取数据库状态并复用原幂等键。

- [ ] **Step 5: 提交**

```bash
git add backend/agent/checkpoint.py backend/agent/runtime.py backend/agent/graphs tests/unit/agent tests/integration/agent
git commit -m "feat: add agent checkpoint and approval resume"
```

### Task 6: 完成错误降级、文档和 Phase 3 验收

**Files:**
- Create: `backend/agent/errors.py`
- Create: `tests/integration/agent/test_multi_agent_workflow.py`
- Create: `docs/architecture/多智能体LangGraph工作流.md`
- Modify: `README.md`
- Modify: `pyproject.toml`

**Interfaces:**
- `class WorkflowError`：错误码、节点、是否可重试和脱敏摘要。
- `class FallbackPolicy`：模型失败、工具未知状态和人工接管策略。
- `async def run_refund_workflow(...)`：完整端到端入口。

- [ ] **Step 1: 写失败验收测试**

```python
async def test_multi_agent_refund_workflow_reaches_audited_result(database_url):
    result = await run_refund_workflow(refund_request(), database_url=database_url)
    assert result.status in {"completed", "awaiting_approval"}
    assert result.trace_id is not None
    assert result.audit_event_ids
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/integration/agent/test_multi_agent_workflow.py -q`

Expected: FAIL because the complete multi-agent entry point and fallback policy do not exist。

- [ ] **Step 3: 实现错误降级、端到端入口和中文文档**

模型格式错误、超时和工具未知状态必须进入受控错误分支；README 增加 LangGraph 实际版本、工作流启动、测试和数据库验证说明；中文架构文档记录主图、子图、State、工具白名单、Checkpoint 和事务边界。

- [ ] **Step 4: 执行 Phase 3 验收**

```powershell
$env:PYTHONNOUSERSITE = "1"
python -m pip check
python -m compileall -q backend tests
python -m pytest tests/unit tests/integration/database tests/integration/agent -q
python -m alembic check
```

Expected: 全部通过；LangGraph 多 Agent 退款闭环覆盖 Supervisor 路由、专业 Agent、工具白名单、审批恢复、跨租户、幂等、审计和降级。

- [ ] **Step 5: 提交 Phase 3 成果**

```bash
git add .
git commit -m "feat: add langgraph multi-agent customer operations workflow"
```
