from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.agent.refund_workflow import RefundWorkflowRequest
from backend.agent.runtime import run_refund_workflow
from backend.agent.state import create_agent_state
from backend.agent.approval_workflow import resume_refund_after_approval
from backend.database.base import TenantScope
from backend.database.models.billing import Refund
from backend.database.models.support import ApprovalRequest
from backend.domain.billing import RefundStatus
from backend.domain.common import DomainError
from backend.domain.approval import ApprovalStatus


def _request(payment, tenant, actor, *, amount: Decimal, key: str, actor_type: str = "user"):
    scope = TenantScope(tenant_id=tenant.id, actor_id=actor.id if actor else None, actor_type=actor_type)
    return RefundWorkflowRequest(
        thread_id=f"security-{uuid4().hex}",
        state=create_agent_state(scope=scope, request_id=uuid4(), message="申请退款"),
        payment_id=payment.id,
        amount=amount,
        refund_idempotency_key=key,
    )


@pytest.mark.asyncio
async def test_cross_tenant_refund_cannot_read_payment(database_url, payment, tenant_b, tenant_a_user):
    request = _request(payment, tenant_b, tenant_a_user, amount=Decimal("20.00"), key=f"cross-{uuid4().hex}")

    with pytest.raises(DomainError, match="payment not found in tenant scope"):
        await run_refund_workflow(request, database_url=database_url)


@pytest.mark.asyncio
async def test_same_idempotency_key_creates_only_one_refund(database_url, session_factory, payment, tenant_a, tenant_a_user):
    key = f"same-{uuid4().hex}"
    first = await run_refund_workflow(
        _request(payment, tenant_a, tenant_a_user, amount=Decimal("20.00"), key=key),
        database_url=database_url,
    )
    second = await run_refund_workflow(
        _request(payment, tenant_a, tenant_a_user, amount=Decimal("20.00"), key=key),
        database_url=database_url,
    )

    assert second.refund_id == first.refund_id
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count(Refund.id)).where(
                Refund.tenant_id == tenant_a.id,
                Refund.idempotency_key == key,
            )
        )
    assert count == 1


@pytest.mark.asyncio
async def test_rejected_approval_does_not_execute_another_refund(database_url, session_factory, payment, tenant_a, tenant_a_user):
    initial = await run_refund_workflow(
        _request(
            payment,
            tenant_a,
            tenant_a_user,
            amount=Decimal("20.00"),
            key=f"approval-{uuid4().hex}",
            actor_type="service",
        ),
        database_url=database_url,
    )

    assert initial.status == "awaiting_approval"
    result = await resume_refund_after_approval(
        database_url=database_url,
        scope=TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user"),
        thread_id=initial.thread_id,
        approval_request_id=initial.approval_request_id,
        approved=False,
        actor_id=tenant_a_user.id,
    )

    assert result.status == "rejected"
    async with session_factory() as session:
        approval = await session.scalar(select(ApprovalRequest).where(ApprovalRequest.id == initial.approval_request_id))
        refund = await session.scalar(select(Refund).where(Refund.id == initial.refund_id))
    assert approval is not None and approval.status is ApprovalStatus.REJECTED
    assert refund is not None and refund.status is RefundStatus.REQUESTED


@pytest.mark.asyncio
async def test_unknown_execution_state_is_not_retried(database_url, session_factory, uow, payment, tenant_a, tenant_a_user):
    unknown = await uow.billing.create_refund_request(
        scope=uow.scope,
        payment_id=payment.id,
        idempotency_key=f"unknown-seed-{uuid4().hex}",
        amount=Decimal("20.00"),
    )
    unknown.status = RefundStatus.UNKNOWN_EXECUTION_STATE
    unknown.has_unknown_execution = True
    await uow.commit()

    request = _request(payment, tenant_a, tenant_a_user, amount=Decimal("20.00"), key=f"retry-{uuid4().hex}")
    with pytest.raises(DomainError, match="unknown execution state refunds must be reconciled"):
        await run_refund_workflow(request, database_url=database_url)

    async with session_factory() as session:
        refunds = list(
            (
                await session.scalars(
                    select(Refund).where(Refund.tenant_id == tenant_a.id, Refund.payment_id == payment.id)
                )
            ).all()
        )
    assert len(refunds) == 1
    assert refunds[0].status is RefundStatus.UNKNOWN_EXECUTION_STATE
