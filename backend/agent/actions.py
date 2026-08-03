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
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.state import KnowledgeEvidence
from backend.agent.tools.billing import BillingTool, RefundToolRequest
from backend.agent.tools.ticket import TicketCreateRequest, TicketTool
from backend.database.base import TenantScope
from backend.database.unit_of_work import UnitOfWork
from backend.domain.common import DomainError
from backend.llm.gateway import ModelGateway

_ACTION_SYSTEM_PROMPT = (
    "你是 CloudDesk 客服意图执行器。判断用户当前这句话要做什么，只输出 JSON。"
    "action 取值：answer(仅需依据知识回答)、request_refund(申请/办理退款)、"
    "create_ticket(创建/提交工单)、list_payments(查询我的扣费/支付记录)。"
)


class ActionDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal["answer", "request_refund", "create_ticket", "list_payments"] = "answer"
    subject: Optional[str] = Field(default=None, max_length=200)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    note: Optional[str] = Field(default=None, max_length=300)


class ActionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: str
    summary: str
    ticket_id: UUID | None = None
    refund_id: UUID | None = None


class ConversationActionExecutor:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def decide(self, gateway: ModelGateway, user_message: str) -> ActionDecision:
        try:
            draft, _ = await gateway.generate_structured(
                system_prompt=_ACTION_SYSTEM_PROMPT,
                user_prompt=user_message,
                response_model=ActionDecision,
            )
            return draft
        except Exception:
            # On any model failure, fall back to a plain answer so the
            # conversation still works.
            return ActionDecision(action="answer")

    async def resolve_customer(self, scope: TenantScope) -> UUID | None:
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            if scope.actor_id is None:
                return None
            return await uow.identity.get_customer_for_user(scope=scope, user_id=scope.actor_id)

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
        return None

    async def _request_refund(self, *, scope: TenantScope, thread_id: str) -> ActionResult | None:
        customer_id = await self.resolve_customer(scope)
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            tool = BillingTool(uow)
            if customer_id is None:
                return ActionResult(
                    action="request_refund",
                    summary="未找到您关联的客户账户，无法直接发起退款，请提供客户信息或联系人工客服。",
                )
            payments = await uow.billing.list_recent_payments(
                scope=scope, customer_id=customer_id, limit=3
            )
            if not payments:
                return ActionResult(
                    action="request_refund",
                    summary="未查询到您名下已成功的支付记录，暂无法发起退款。",
                )
            payment = payments[0]
            # Idempotency keyed by thread so repeated turns do not double-refund.
            idempotency_key = f"chat-{thread_id}-{str(payment.id)[:8]}"
            try:
                refund = await tool.request(
                    RefundToolRequest(
                        scope=scope,
                        payment_id=payment.id,
                        idempotency_key=idempotency_key,
                        amount=payment.amount,
                    )
                )
            except DomainError as exc:
                return ActionResult(action="request_refund", summary=f"退款申请未通过校验：{exc}")
            status = refund.status.value if hasattr(refund.status, "value") else str(refund.status)
            return ActionResult(
                action="request_refund",
                summary=(
                    f"已为您针对最近一笔成功支付（金额 {payment.amount} 元）创建退款申请，"
                    f"退款单号 {refund.id}，当前状态：{status}。"
                    "若金额较高将进入人工审批，审批通过后自动执行。"
                ),
                refund_id=refund.id,
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
