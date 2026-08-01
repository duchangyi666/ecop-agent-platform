from __future__ import annotations

import pytest
from sqlalchemy import func, select

from backend.database.base import TenantScope
from backend.database.models.support import Ticket


@pytest.mark.asyncio
async def test_repository_cannot_read_other_tenant_payment(uow, tenant_b, payment):
    result = await uow.billing.get_payment_for_tenant(
        scope=TenantScope(tenant_id=tenant_b.id),
        payment_id=payment.id,
    )

    assert result is None


@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_on_exception(session_factory, tenant_a, customer_id, tenant_a_user):
    from backend.database.unit_of_work import UnitOfWork

    uow = UnitOfWork(
        session_factory=session_factory,
        scope=TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user"),
    )

    with pytest.raises(RuntimeError, match="force rollback"):
        async with uow:
            await uow.support.create_ticket(
                scope=TenantScope(tenant_id=tenant_a.id),
                customer_id=customer_id,
                subject="rollback",
                priority="normal",
            )
            raise RuntimeError("force rollback")

    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(Ticket).where(Ticket.subject == "rollback"))

    assert count == 0
