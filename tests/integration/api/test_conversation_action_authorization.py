from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.agent.actions import ActionDecision, ActionResult, ConversationActionExecutor
from backend.auth.permissions import Permission
from backend.database.base import TenantScope
from backend.database.models.identity import User
from backend.database.models.billing import CustomerContact, Payment, Refund
from backend.database.models.support import ApprovalRequest, Ticket


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "permission", "method"),
    [
        ("request_refund", Permission.REFUND_REQUEST, "_request_refund"),
        ("create_ticket", Permission.TICKET_CREATE, "_create_ticket"),
        ("query_ticket_status", Permission.TICKET_READ, "_query_ticket_status"),
    ],
)
async def test_conversation_action_requires_its_own_permission(
    session_factory, tenant_a, tenant_a_user, grant_permission, monkeypatch,
    action, permission, method,
):
    await grant_permission(tenant_a_user.id, Permission.CUSTOMER_CONSULT)
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    executor = ConversationActionExecutor(session_factory)
    operation = AsyncMock(return_value=ActionResult(action=action, summary="completed"))
    monkeypatch.setattr(executor, method, operation)
    decision = ActionDecision(action=action)

    denied = await executor.execute(
        scope=scope, decision=decision, user_message="test", thread_id="test-thread",
    )
    operation.assert_not_awaited()
    assert denied is not None and "权限" in denied.summary

    await grant_permission(tenant_a_user.id, permission)
    allowed = await executor.execute(
        scope=scope, decision=decision, user_message="test", thread_id="test-thread",
    )
    operation.assert_awaited_once()
    assert allowed is not None and allowed.summary == "completed"

    operation.reset_mock()
    async with session_factory() as session:
        user = await session.get(User, tenant_a_user.id)
        user.status = "disabled"
        await session.commit()
    denied = await executor.execute(
        scope=scope, decision=decision, user_message="test", thread_id="test-thread",
    )
    operation.assert_not_awaited()
    assert denied is not None and "权限" in denied.summary


@pytest.mark.asyncio
async def test_repeated_chat_refund_reuses_approval_across_threads(
    session_factory, tenant_a, tenant_a_user, payment, grant_permission,
):
    await grant_permission(tenant_a_user.id, Permission.CUSTOMER_CONSULT)
    async with session_factory() as session:
        stored_payment = await session.get(Payment, payment.id)
        stored_payment.amount = Decimal("1500.00")
        session.add(CustomerContact(
            tenant_id=tenant_a.id, customer_id=payment.customer_id, user_id=tenant_a_user.id,
            channel="email", masked_value="test@example.invalid", contact_hash=uuid4().hex,
            preferred_language="zh-CN",
        ))
        session.add(Payment(
            tenant_id=tenant_a.id, customer_id=payment.customer_id, invoice_id=payment.invoice_id,
            external_payment_id=f"repeat-{uuid4().hex}", amount=Decimal("1500.00"),
            currency=payment.currency, status=payment.status, paid_at=payment.paid_at + timedelta(minutes=1),
        ))
        await session.commit()
    executor = ConversationActionExecutor(session_factory)
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    decision = ActionDecision(action="request_refund")
    denied = await executor.execute(scope=scope, decision=decision, user_message="退款", thread_id="denied")
    assert denied is not None and "权限" in denied.summary
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Refund).where(Refund.tenant_id == tenant_a.id)) == 0
    await grant_permission(tenant_a_user.id, Permission.REFUND_REQUEST)
    first, second = await asyncio.gather(
        executor.execute(scope=scope, decision=decision, user_message="退款", thread_id="repeat-one"),
        executor.execute(scope=scope, decision=decision, user_message="退款", thread_id="repeat-two"),
    )
    third = await executor.execute(scope=scope, decision=decision, user_message="退款", thread_id="repeat-three")
    assert first.refund_id == second.refund_id
    assert first.approval_request_id == second.approval_request_id
    assert third.refund_id == first.refund_id
    assert third.approval_request_id == first.approval_request_id
    async with session_factory() as session:
        approvals = list(await session.scalars(
            select(ApprovalRequest).where(ApprovalRequest.refund_id == first.refund_id)
        ))
    assert len(approvals) == 1


@pytest.mark.asyncio
async def test_ticket_action_does_not_write_without_ticket_permission(
    session_factory, tenant_a, tenant_a_user, customer_id, grant_permission,
):
    await grant_permission(tenant_a_user.id, Permission.CUSTOMER_CONSULT)
    async with session_factory() as session:
        session.add(CustomerContact(
            tenant_id=tenant_a.id, customer_id=customer_id, user_id=tenant_a_user.id,
            channel="email", masked_value="test@example.invalid", contact_hash=uuid4().hex,
            preferred_language="zh-CN",
        ))
        await session.commit()
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    executor = ConversationActionExecutor(session_factory)
    decision = ActionDecision(action="create_ticket", subject="权限测试")
    result = await executor.execute(scope=scope, decision=decision, user_message="登录故障", thread_id="ticket-test")
    assert result is not None and "权限" in result.summary
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Ticket).where(Ticket.tenant_id == tenant_a.id)) == 0

    await grant_permission(tenant_a_user.id, Permission.TICKET_CREATE)
    result = await executor.execute(scope=scope, decision=decision, user_message="登录故障", thread_id="ticket-test")
    assert result is not None and result.ticket_id is not None
    async with session_factory() as session:
        ticket = await session.get(Ticket, result.ticket_id)
        assert ticket.customer_id == customer_id
