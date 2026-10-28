from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.database.models.billing import Refund
from backend.domain.common import DomainError


@pytest.mark.asyncio
async def test_duplicate_refund_idempotency_key_returns_existing_row(uow, payment):
    created = await uow.billing.create_refund_request(
        scope=uow.scope,
        payment_id=payment.id,
        idempotency_key="task7-refund-1",
        amount=Decimal("20.00"),
    )
    returned = await uow.billing.create_refund_request(
        scope=uow.scope,
        payment_id=payment.id,
        idempotency_key="task7-refund-1",
        amount=Decimal("20.00"),
    )
    await uow.commit()

    assert returned.id == created.id


@pytest.mark.asyncio
async def test_duplicate_refund_idempotency_key_does_not_create_second_row(session_factory, uow, tenant_a, payment):
    await uow.billing.create_refund_request(
        scope=uow.scope,
        payment_id=payment.id,
        idempotency_key="task7-refund-2",
        amount=Decimal("20.00"),
    )
    await uow.billing.create_refund_request(
        scope=uow.scope,
        payment_id=payment.id,
        idempotency_key="task7-refund-2",
        amount=Decimal("20.00"),
    )
    await uow.commit()

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(Refund)
            .where(Refund.tenant_id == tenant_a.id, Refund.idempotency_key == "task7-refund-2")
        )

    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["payment", "amount"])
async def test_refund_idempotency_key_rejects_changed_parameters(uow, payment, changed):
    await uow.billing.create_refund_request(
        scope=uow.scope, payment_id=payment.id, idempotency_key="same-key", amount=Decimal("20.00"),
    )
    with pytest.raises(DomainError, match="idempotency key"):
        await uow.billing.create_refund_request(
            scope=uow.scope,
            payment_id=uuid4() if changed == "payment" else payment.id,
            idempotency_key="same-key",
            amount=Decimal("21.00") if changed == "amount" else Decimal("20.00"),
        )
