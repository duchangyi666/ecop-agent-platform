from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.agent.refund_workflow import RefundWorkflowRequest
from backend.agent.runtime import run_refund_workflow
from backend.agent.state import create_agent_state
from backend.database.base import TenantScope
from backend.database.models.billing import Refund
from backend.database.models.support import ApprovalRequest
from backend.domain.billing import RefundStatus
from backend.domain.common import DomainError


def make_refund_workflow_request(payment, tenant, actor, amount: Decimal, key: str | None = None):
    scope = TenantScope(
        tenant_id=tenant.id,
        actor_id=actor.id if actor is not None else None,
        actor_type="user",
    )
    return RefundWorkflowRequest(
        thread_id=f"thread-refund-{uuid4().hex}",
        state=create_agent_state(
            scope=scope,
            request_id=uuid4(),
            message="我要申请退款",
        ),
        payment_id=payment.id,
        amount=amount,
        refund_idempotency_key=key or f"refund-{uuid4().hex}",
    )


@pytest.mark.asyncio
async def test_low_risk_refund_is_persisted_as_requested(database_url, session_factory, payment, tenant_a, tenant_a_user):
    request = make_refund_workflow_request(payment, tenant_a, tenant_a_user, Decimal("20.00"))

    result = await run_refund_workflow(request, database_url=database_url)

    assert result.status == "refund_requested"
    assert result.refund_id is not None
    assert result.trace_id is not None
    async with session_factory() as session:
        refund = await session.scalar(select(Refund).where(Refund.id == result.refund_id))
    assert refund is not None
    assert refund.status is RefundStatus.REQUESTED


@pytest.mark.asyncio
async def test_cross_tenant_payment_is_not_refundable(database_url, tenant_b, tenant_a_user, payment):
    request = make_refund_workflow_request(payment, tenant_b, None, Decimal("20.00"))

    with pytest.raises(DomainError, match="payment not found in tenant scope"):
        await run_refund_workflow(request, database_url=database_url)


@pytest.mark.asyncio
async def test_concurrent_refund_retries_reuse_approval(database_url, session_factory, payment, tenant_a, tenant_a_user):
    request = make_refund_workflow_request(payment, tenant_a, tenant_a_user, Decimal("20.00"))
    request.state.tenant_scope = TenantScope(
        tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="service",
    )
    first, second = await asyncio.gather(
        run_refund_workflow(request.model_copy(deep=True), database_url=database_url),
        run_refund_workflow(request.model_copy(deep=True), database_url=database_url),
    )
    assert first.refund_id == second.refund_id
    assert first.approval_request_id == second.approval_request_id
    async with session_factory() as session:
        approvals = list(await session.scalars(
            select(ApprovalRequest).where(ApprovalRequest.refund_id == first.refund_id)
        ))
    assert len(approvals) == 1
