# 多智能体 LangGraph 最终工作流设计

## 1. 目标

平台采用 LangGraph 作为多 Agent 编排核心，建立一张可恢复、可审计、可按租户隔离的主工作流。主图包含 Supervisor Agent 和多个职责边界明确的专业 Agent 子图：客服对话 Agent、知识检索 Agent、计费退款 Agent、工单 Agent 和审批协同 Agent。

第一条完整业务链为“退款/计费异常处理”，但 State、消息协议、工具注册表、Checkpoint 和事务入口按最终架构设计，后续增加业务能力时只扩展 Agent 子图和工具，不替换主图。

## 2. 技术基线

当前隔离环境实际版本：Python `3.11.15`、LangGraph `1.0.9`、LangChain Core `1.2.16`、LangGraph Checkpoint `2.1.2`、LangGraph Prebuilt `1.0.8`、LangGraph SDK `0.3.15`。项目直接依赖以实际环境为准，禁止为了套用示例而降级现有版本。

## 3. 总体架构

```text
请求接入
  ↓
LangGraph 主图：标准化 → 恢复 Checkpoint → Supervisor Agent
  ↓ 条件路由
┌────────────────┬────────────────┬────────────────┐
│ 客服对话 Agent │ 知识检索 Agent │ 计费退款 Agent │
│ 子图           │ 子图           │ 子图           │
└────────────────┴────────────────┴────────────────┘
        ↓                 ↓                 ↓
        └──────────── Supervisor 汇总 ─────┘
                              ↓
                 策略校验 / 人工审批 / 工具执行
                              ↓
              工单 Agent → 回复 Agent → 审计与 Checkpoint
```

Supervisor 负责理解任务、选择专业 Agent 和汇总结果；专业 Agent 负责自己的领域推理；确定性策略节点负责权限、金额、租户、状态转换和审批条件；工具节点负责真实副作用。任何 Agent 都不能直接写数据库或调用未注册工具。

## 4. Agent 角色边界

| Agent | 允许职责 | 禁止职责 |
| --- | --- | --- |
| Supervisor Agent | 识别任务类型、选择 Agent、汇总结构化结果、决定是否继续 | 直接退款、直接改工单、绕过策略节点 |
| 客服对话 Agent | 理解客户表达、追问缺失信息、生成客服回复 | 编造支付状态或审批结论 |
| 知识检索 Agent | 生成检索请求、筛选证据、输出引用摘要 | 直接修改知识库或把无证据内容当事实 |
| 计费退款 Agent | 查询支付/发票、生成退款预览、解释账单异常 | 绕过幂等、权限和人工审批执行退款 |
| 工单 Agent | 创建、更新、分配工单，记录事件 | 修改不属于当前租户的工单 |
| 审批协同 Agent | 准备审批材料、解释风险、跟踪审批状态 | 自行批准高风险操作 |

风险策略、金额校验、权限校验、状态机转换和最终工具授权由确定性代码完成，不能交给模型自由决定。

## 5. 统一 AgentState

```python
class AgentState(TypedDict, total=False):
    request_id: UUID
    tenant_scope: TenantScope
    customer_id: UUID | None
    conversation: list[Message]
    task: TaskContext
    supervisor_decision: SupervisorDecision | None
    specialist_result: SpecialistResult | None
    retrieval_context: list[Evidence]
    billing_context: BillingContext | None
    ticket_context: TicketContext | None
    approval: ApprovalState
    tool_calls: list[ToolCallRecord]
    next_action: NextAction
    response_draft: str | None
    final_response: str | None
    errors: list[WorkflowError]
    trace_id: UUID
    audit_event_ids: list[UUID]
```

State 只保存脱敏摘要、业务 ID、哈希和恢复所需字段，不保存 API Key、银行卡号、原始系统 Prompt、完整敏感工具参数或未脱敏客户隐私。

## 6. 主图和专业 Agent 子图

主图使用 `StateGraph(AgentState)`，通过 `add_conditional_edges` 将 Supervisor 的结构化决策路由到专业 Agent 子图。每个专业 Agent 子图内部仍使用 LangGraph StateGraph，拥有自己的局部 State，但只能通过 `SpecialistResult` 写回主 State。

主图节点：

1. `normalize_request`：建立不可变 `TenantScope` 和 `request_id`。
2. `load_checkpoint`：读取恢复状态，并重新从数据库确认业务状态。
3. `supervisor_agent`：输出受控的 Agent 路由决策。
4. `route_specialist`：根据决策进入专业 Agent 子图。
5. `policy_gate`：检查权限、风险、金额和状态转换。
6. `approval_or_tool`：进入审批、工具预览或工具执行。
7. `ticket_agent`：创建/更新工单和工单事件。
8. `response_agent`：基于结构化业务结果生成回复。
9. `persist_trace`：写入 RuntimeTrace、RuntimeSpan、ToolExecution、审计和 Checkpoint。

专业子图：

- 客服对话子图：理解、追问、回复草稿。
- 知识检索子图：检索、证据筛选、引用摘要。
- 计费退款子图：账单上下文、退款预览、异常解释。
- 工单子图：工单读取、状态转换、事件和分配。
- 审批子图：审批材料、审批状态读取、恢复执行。

## 7. Agent 消息与工具协议

Agent 之间不传自然语言指令作为控制协议，而传结构化消息：

```python
class AgentMessage(TypedDict):
    sender: str
    recipient: str
    message_type: Literal["request", "result", "clarification", "handoff"]
    request_id: UUID
    payload: dict[str, object]
    confidence: float | None
    evidence_ids: list[str]
```

工具通过注册表暴露：

```python
class ToolContract(Protocol):
    name: str
    owner_agent: str
    risk_level: str
    requires_approval: bool

    async def preview(self, request: ToolRequest) -> ToolPreview: ...
    async def execute(self, request: ToolRequest) -> ToolResult: ...
```

计费退款 Agent 只能使用账单查询、退款预览和退款执行工具；工单 Agent 只能使用工单查询、创建、更新和分配工具。工具执行必须携带租户作用域、操作者、幂等键、超时和脱敏结果摘要。

## 8. 路由、审批和恢复

Supervisor 输出的 `next_action` 只能是：`route_customer`、`route_knowledge`、`route_billing`、`route_ticket`、`route_approval`、`ask_clarification`、`human_handoff`、`finish`。

退款业务链：

```text
客户请求退款
→ Supervisor Agent
→ 计费退款 Agent 子图
→ 查询支付和退款历史
→ policy_gate 校验金额、租户、权限和未知执行状态
→ 低风险执行，或审批协同 Agent 创建审批
→ 审批通过后使用原幂等键恢复
→ 工单 Agent 记录事件
→ 客服对话 Agent 生成回复
```

高风险、权限不足或策略不确定时，工作流必须在审批前保存 Checkpoint。恢复时重新读取数据库中的审批和退款状态，不能只信任旧 State。

## 9. 事务、Checkpoint 和可观测性

- 业务写入使用 Phase 2 的 `UnitOfWork`，退款、审批动作、工单事件和审计在明确事务边界内提交或回滚。
- 外部工具调用不与长数据库事务绑定；执行前保存意图和幂等键，执行后记录结果状态。
- Checkpoint 保存主图状态版本、当前 Agent、下一动作、业务 ID、脱敏摘要和 Trace ID。
- 运行追踪记录 Agent、节点、工具、耗时、重试、模型摘要、成本和错误摘要。
- 租户过滤由 Repository 保证，Agent 不能从客户输入覆盖 `TenantScope`。

第一版先定义 CheckpointStore 接口，并提供测试内存实现；生产实现使用 PostgreSQL 持久化，不能把 Checkpoint 与业务表状态混用。

## 10. 错误和降级

- 模型超时、临时网络错误、限流：有限次重试，超过上限转人工或创建工单。
- 权限不足、金额非法、状态非法、租户不匹配：不重试，返回业务结果。
- 工具返回未知执行状态：禁止自动重复执行，进入对账和人工处理。
- Agent 输出格式错误：由结构化输出校验捕获，重试一次后转人工。
- 回复 Agent 失败：返回固定处理中提示，保留请求号、工单号或审批号。

## 11. 测试策略

- AgentState 合并、租户不可覆盖、Checkpoint 恢复和敏感字段脱敏。
- Supervisor 路由到正确专业 Agent，拒绝未注册 Agent。
- 各专业子图输出结构化 `SpecialistResult`。
- 高风险退款进入审批，审批通过使用原幂等键恢复。
- Agent 工具白名单、跨租户隔离、权限和金额校验。
- PostgreSQL 集成验证退款、工单事件、审计和 RuntimeTrace 的事务一致性。
- LangGraph 图结构、条件边、异常恢复和 Phase 2 全量回归。

## 12. 实施边界

1. 先冻结 State、AgentMessage、SupervisorDecision、SpecialistResult 和 ToolContract。
2. 实现 LangGraph 主图、Supervisor 路由和空的专业 Agent 子图。
3. 实现客服、知识、计费退款、工单、审批五个专业子图。
4. 接入退款 preview、策略、审批、execute 和原幂等键恢复。
5. 接入 Checkpoint、RuntimeTrace、审计、错误重试和降级。
6. 用真实 PostgreSQL 完成多 Agent 退款/计费异常端到端验收。
