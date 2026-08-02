from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from backend.database.base import TenantScope
from backend.database.unit_of_work import UnitOfWork
from backend.domain.approval import ApprovalStatus
from backend.domain.common import DomainError


@pytest.mark.asyncio
async def test_create_refund_approval_request_is_tenant_scoped(uow, payment, tenant_a, tenant_a_user) -> None:
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    refund = await uow.billing.create_refund_request(
        scope=scope,
        payment_id=payment.id,
        idempotency_key=f"approval-{uuid4().hex}",
        amount=Decimal("20.00"),
    )

    approval = await uow.support.create_refund_approval_request(
        scope=scope,
        refund_id=refund.id,
        action="approve_refund",
        payload={"amount": "20.00", "payment_id": str(payment.id)},
        approval_role="finance_manager",
        checkpoint_reference="thread-refund-1",
    )

    assert approval.refund_id == refund.id
    assert approval.ticket_id is None
    assert approval.status is ApprovalStatus.PENDING


@pytest.mark.asyncio
async def test_create_refund_approval_request_rejects_cross_tenant_refund(
    session_factory,
    payment,
    tenant_b,
    tenant_a,
    tenant_a_user,
) -> None:
    source_scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    async with UnitOfWork(session_factory, scope=source_scope) as source_uow:
        refund = await source_uow.billing.create_refund_request(
            scope=source_scope,
            payment_id=payment.id,
            idempotency_key=f"cross-tenant-{uuid4().hex}",
            amount=Decimal("20.00"),
        )

    foreign_scope = TenantScope(tenant_id=tenant_b.id)
    async with UnitOfWork(session_factory, scope=foreign_scope) as foreign_uow:
        with pytest.raises(DomainError, match="refund not found in tenant scope"):
            await foreign_uow.support.create_refund_approval_request(
                scope=foreign_scope,
                refund_id=refund.id,
                action="approve_refund",
                payload={"amount": "20.00"},
                approval_role="finance_manager",
                checkpoint_reference="thread-cross-tenant",
            )
