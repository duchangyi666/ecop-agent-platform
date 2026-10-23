"""Conversation action executor: connects the LLM dialogue to real business ops.

The customer-service model decides whether the user's message is a pure
question (answer with knowledge) or a business request (refund / ticket /
payment lookup). For business requests this module resolves the acting
user's customer and invokes the real BillingTool / TicketTool against the
PostgreSQL business tables, returning a human-readable summary that is
grounded into the final answer and surfaced as an evidence card.
"""

from __future__ import annotations

from typing import Literal, Optional
from datetime import timedelta
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.state import ConversationMessage, KnowledgeEvidence
from backend.agent.policies.risk import HIGH_RISK_REFUND_THRESHOLD
from backend.agent.tools.billing import BillingTool, RefundToolRequest
from backend.core.retry import with_retry
from backend.agent.tools.ticket import TicketCreateRequest, TicketTool
from backend.database.base import TenantScope
from backend.database.unit_of_work import UnitOfWork
from backend.domain.common import DomainError
from backend.llm.gateway import ModelGateway

_ACTION_SYSTEM_PROMPT = (
    "你是 CloudDesk 客服的判断中枢，像经验丰富的客服主管一样审慎，不是命令执行器。"
    "结合对话历史判断用户当前这句话的意图与是否具备执行条件，只输出 JSON。"
    "action 取值：answer(纯咨询/需解释/需拒绝)、request_refund(反映重复扣费或要求退款)、"
    "create_ticket(创建/提交工单)、list_payments(查我的扣费/支付记录)、"
    "query_ticket_status(问工单进度/处理到哪了)、query_refund_status(问退款进度/到账了吗)。\n"
    "原则：\n"
    "- 纯咨询政策、或要求越权/绕过审批/明显不当时，用 answer（由回复环节解释或礼貌拒绝），不要执行。\n"
    "- 用户问“我的工单/退款/扣费怎么样了”这类需要看真实数据的，用对应查询动作，系统会去查业务库再回答。\n"
    "- create_ticket：只说“建个工单”而没说是什么问题，ready=false 并在 question 只问一个问题；"
    "已说明具体问题则 ready=true 并在 subject 概括主题。\n"
    "- request_refund：用户反映重复扣费/要求退款时用此动作；系统会自动核实是否真的存在重复扣费，"
    "若不存在会如实告知并不退款，因此无需担心误退。若用户只是问退款政策，用 answer。"
)


class ActionDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal[
        "answer",
        "request_refund",
        "create_ticket",
        "list_payments",
        "query_ticket_status",
        "query_refund_status",
    ] = "answer"
    ready: bool = True
    question: Optional[str] = Field(default=None, max_length=300)
    subject: Optional[str] = Field(default=None, max_length=200)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    note: Optional[str] = Field(default=None, max_length=300)


class ActionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: str
    summary: str
    ticket_id: UUID | None = None
    refund_id: UUID | None = None
    approval_request_id: UUID | None = None


class ConversationActionExecutor:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def decide(
        self,
        gateway: ModelGateway,
        user_message: str,
        conversation: list[ConversationMessage] | None = None,
    ) -> ActionDecision:
        lines: list[str] = []
        for message in conversation or []:
            speaker = "用户" if message.role == "user" else "客服"
            lines.append(f"{speaker}：{message.content}")
        user_prompt = "\n".join(lines) or user_message
        try:
            draft, _ = await gateway.generate_structured(
                system_prompt=_ACTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=ActionDecision,
            )
            if isinstance(draft, ActionDecision):
                return draft
            # Non-conforming gateway (e.g. the offline fake) → coerce safely.
            return ActionDecision.model_validate(draft.model_dump())
        except Exception:
            # On any model failure, fall back to a plain answer so the
            # conversation still works.
            return ActionDecision(action="answer")

    async def resolve_customer(self, scope: TenantScope) -> UUID | None:
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            if scope.actor_id is None:
                return None
            return await uow.identity.get_customer_for_user(scope=scope, user_id=scope.actor_id)

    _DOMAIN_ACTIONS: dict[str, tuple[str, ...]] = {
        "route_billing": ("request_refund", "query_refund_status", "list_payments"),
        "route_ticket": ("create_ticket", "query_ticket_status"),
        "route_approval": ("query_refund_status",),
        "route_knowledge": (),
        "route_customer": (),
    }

    async def run_domain_action(
        self,
        gateway: ModelGateway | None,
        state,
        *,
        domain: str,
        user_message: str,
        thread_id: str,
    ) -> tuple[ActionResult | None, str | None]:
        """Two-level multi-agent routing: the LLM supervisor picked `domain`;
        here the domain agent confirms the concrete action and executes it.
        Returns (action_result, clarification)."""
        allowed = self._DOMAIN_ACTIONS.get(domain, ())
        if not allowed or gateway is None:
            return None, None
        decision = await self.decide(gateway, user_message, conversation=state.conversation)
        if decision.action not in allowed:
            # The domain was routed but the concrete intent differs; do not
            # force an unrelated business action.
            return None, None
        if not decision.ready and decision.question:
            return None, decision.question
        # Three-layer resilience around the business tool execution: transient
        # failures retry, then degrade to "no action" so the conversation can
        # still answer from knowledge instead of crashing.
        wrapped = with_retry(
            agent_type=domain,
            agent_fallback=lambda exc: None,
            system_fallback=lambda exc: None,
        )(self.execute)
        try:
            result = await wrapped(
                scope=state.tenant_scope,
                decision=decision,
                user_message=user_message,
                thread_id=thread_id,
            )
        except DomainError:
            result = None
        return result, None

    async def execute(
        self,
        *,
        scope: TenantScope,
        decision: ActionDecision,
        user_message: str,
        thread_id: str,
    ) -> ActionResult | None:
        if decision.action == "answer":
            return None
        if decision.action == "request_refund":
            return await self._request_refund(scope=scope, thread_id=thread_id)
        if decision.action == "create_ticket":
            return await self._create_ticket(scope=scope, decision=decision, user_message=user_message)
        if decision.action == "list_payments":
            return await self._list_payments(scope=scope)
        if decision.action == "query_ticket_status":
            return await self._query_ticket_status(scope=scope)
        if decision.action == "query_refund_status":
            return await self._query_refund_status(scope=scope)
        return None

    async def _query_ticket_status(self, *, scope: TenantScope) -> ActionResult | None:
        customer_id = await self.resolve_customer(scope)
        if customer_id is None:
            return ActionResult(action="query_ticket_status", summary="未找到您关联的客户账户，无法查询工单。")
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            tickets = await uow.support.list_tickets_for_customer(
                scope=scope, customer_id=customer_id, limit=3
            )
        if not tickets:
            return ActionResult(action="query_ticket_status", summary="您名下暂时没有工单记录。")
        lines = [
            f"- 「{t.subject}」当前状态：{t.status.value if hasattr(t.status,'value') else t.status}"
            for t in tickets
        ]
        return ActionResult(
            action="query_ticket_status",
            summary="我查到您最近的工单：\n" + "\n".join(lines),
        )

    async def _query_refund_status(self, *, scope: TenantScope) -> ActionResult | None:
        customer_id = await self.resolve_customer(scope)
        if customer_id is None:
            return ActionResult(action="query_refund_status", summary="未找到您关联的客户账户，无法查询退款。")
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            refunds = await uow.billing.list_refunds_for_customer(
                scope=scope, customer_id=customer_id, limit=3
            )
        if not refunds:
            return ActionResult(action="query_refund_status", summary="您名下暂时没有退款记录。")
        lines = [
            f"- 退款 {r.amount} 元，状态：{r.status.value if hasattr(r.status,'value') else r.status}"
            for r in refunds
        ]
        return ActionResult(
            action="query_refund_status",
            summary="我查到您最近的退款：\n" + "\n".join(lines),
        )

    @staticmethod
    def _find_duplicate(payments) -> object | None:
        """Return the later payment of a same-amount pair within 24h, if any."""
        ordered = sorted(payments, key=lambda p: p.paid_at)
        for i, first in enumerate(ordered):
            for second in ordered[i + 1 :]:
                if second.amount == first.amount and (
                    second.paid_at - first.paid_at
                ) <= timedelta(hours=24):
                    return second
        return None

    async def _request_refund(self, *, scope: TenantScope, thread_id: str) -> ActionResult | None:
        customer_id = await self.resolve_customer(scope)
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            tool = BillingTool(uow)
            if customer_id is None:
                return ActionResult(
                    action="request_refund",
                    summary="未找到您关联的客户账户，无法核实扣费记录，请联系人工客服。",
                )
            payments = await uow.billing.list_recent_payments(
                scope=scope, customer_id=customer_id, limit=10
            )
            if not payments:
                return ActionResult(
                    action="request_refund",
                    summary="我核对了您名下的支付记录，没有查询到已成功的支付，暂无法认定重复扣费。",
                )
            duplicate = self._find_duplicate(payments)
            if duplicate is None:
                checked = "、".join(f"{p.paid_at:%m-%d} {p.amount}元" for p in payments[:4])
                return ActionResult(
                    action="request_refund",
                    summary=(
                        f"我逐笔核对了您最近的成功支付（{checked}），未发现 24 小时内相同金额的重复扣费，"
                        "因此暂时不能为您发起退款。若您确认有重复扣款，请提供具体的扣费流水号或时间，"
                        "我再为您进一步核查，或为您转人工。"
                    ),
                )
            # Idempotency keyed by the payment so the same duplicate charge is
            # never refunded twice, regardless of conversation thread/turn.
            idempotency_key = f"chat-refund-{duplicate.id}"
            try:
                refund = await tool.request(
                    RefundToolRequest(
                        scope=scope,
                        payment_id=duplicate.id,
                        idempotency_key=idempotency_key,
                        amount=duplicate.amount,
                    )
                )
            except DomainError as exc:
                return ActionResult(action="request_refund", summary=f"退款申请未通过校验：{exc}")
            status = refund.status.value if hasattr(refund.status, "value") else str(refund.status)
            approval_request_id: UUID | None = None
            approval_note = ""
            if duplicate.amount >= HIGH_RISK_REFUND_THRESHOLD:
                checkpoint = await uow.governance.get_workflow_checkpoint(
                    scope=scope, thread_id=thread_id
                )
                existing_approval_id = (
                    (checkpoint.state_summary or {}).get("approval_request_id")
                    if checkpoint is not None
                    else None
                )
                if existing_approval_id:
                    approval_request_id = UUID(str(existing_approval_id))
                    approval_note = (
                        f" 该金额需要财务经理审批，审批单 {approval_request_id} 正在等待处理。"
                    )
                else:
                    approval = await uow.support.create_refund_approval_request(
                        scope=scope,
                        refund_id=refund.id,
                        action="approve_refund",
                        payload={
                            "amount": str(duplicate.amount),
                            "payment_id": str(duplicate.id),
                            "refund_id": str(refund.id),
                            "source": "customer_chat",
                        },
                        approval_role="finance_manager",
                        checkpoint_reference=thread_id,
                    )
                    approval_request_id = approval.id
                    await uow.governance.save_workflow_checkpoint(
                        scope=scope,
                        thread_id=thread_id,
                        state_summary={
                            "thread_id": thread_id,
                            "refund_id": str(refund.id),
                            "approval_request_id": str(approval.id),
                            "next_action": "human_handoff",
                        },
                        refund_idempotency_key=idempotency_key,
                        status="awaiting_approval",
                        trace_id=None,
                    )
                    approval_note = (
                        f" 该金额达到审批门槛，已提交财务经理审批，审批单号 {approval.id}。"
                    )
            return ActionResult(
                action="request_refund",
                summary=(
                    f"经核实，您确有一笔重复扣费（{duplicate.paid_at:%m-%d} {duplicate.amount} 元，"
                    "24 小时内出现两笔相同金额）。我已为您创建退款申请，"
                    f"退款单号 {refund.id}，当前状态：{status}。"
                    f"{approval_note}"
                ),
                refund_id=refund.id,
                approval_request_id=approval_request_id,
            )

    async def _create_ticket(
        self, *, scope: TenantScope, decision: ActionDecision, user_message: str
    ) -> ActionResult | None:
        customer_id = await self.resolve_customer(scope)
        if customer_id is None:
            return ActionResult(
                action="create_ticket",
                summary="未找到您关联的客户账户，无法创建工单，请联系人工客服。",
            )
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            tool = TicketTool(uow)
            result = await tool.create(
                TicketCreateRequest(
                    scope=scope,
                    customer_id=customer_id,
                    subject=(decision.subject or user_message)[:255],
                    priority=decision.priority,
                    description_summary=user_message[:2000],
                    message=user_message[:2000],
                )
            )
        return ActionResult(
            action="create_ticket",
            summary=(
                f"已为您创建工单，工单号 {result.ticket_id}，主题「{result.subject}」，"
                f"当前状态：{result.status}。您可以在「我的工单」中查看处理进度。"
            ),
            ticket_id=result.ticket_id,
        )

    async def _list_payments(self, *, scope: TenantScope) -> ActionResult | None:
        customer_id = await self.resolve_customer(scope)
        if customer_id is None:
            return ActionResult(
                action="list_payments",
                summary="未找到您关联的客户账户，无法查询支付记录。",
            )
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            payments = await uow.billing.list_recent_payments(
                scope=scope, customer_id=customer_id, limit=5
            )
        if not payments:
            return ActionResult(action="list_payments", summary="未查询到您名下的成功支付记录。")
        lines = [
            f"- {p.paid_at:%Y-%m-%d} 金额 {p.amount} 元（流水 {p.external_payment_id}）"
            for p in payments
        ]
        return ActionResult(
            action="list_payments",
            summary="您最近的成功支付记录如下：\n" + "\n".join(lines),
        )


def action_to_evidence(result: ActionResult) -> KnowledgeEvidence:
    """Surface a business action result as an evidence card for the UI/prompt."""
    return KnowledgeEvidence(
        document_id=uuid4(),
        external_document_id=f"action-{result.action}",
        title="业务执行结果",
        source_uri=None,
        content_snippet=result.summary,
        score=1.0,
    )


__all__ = [
    "ActionDecision",
    "ActionResult",
    "ConversationActionExecutor",
    "action_to_evidence",
]
