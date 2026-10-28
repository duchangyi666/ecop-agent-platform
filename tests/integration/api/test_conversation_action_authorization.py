from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.agent.actions import ActionDecision, ActionResult, ConversationActionExecutor
from backend.auth.permissions import Permission
from backend.database.base import TenantScope
from backend.database.models.identity import User
from backend.database.models.billing import CustomerContact, Payment
from backend.database.models.support import ApprovalRequest


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
    await grant_permission(tenant_a_user.id, Permission.REFUND_REQUEST)
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

