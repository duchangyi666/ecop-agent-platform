from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from backend.database.models.billing import Customer


@pytest.mark.asyncio
async def test_rls_customer_select_is_tenant_scoped(
    session_factory,
    tenant_a,
    tenant_b,
) -> None:
    external_a = f"rls-a-{uuid4().hex[:8]}"
    external_b = f"rls-b-{uuid4().hex[:8]}"
    async with session_factory() as session:
        session.add_all(
            [
                Customer(
                    id=uuid4(),
                    tenant_id=tenant_a.id,
                    name="RLS Tenant A",
                    external_customer_id=external_a,
                    support_tier="standard",
                    status="active",
                ),
                Customer(
                    id=uuid4(),
                    tenant_id=tenant_b.id,
                    name="RLS Tenant B",
                    external_customer_id=external_b,
                    support_tier="standard",
                    status="active",
                ),
            ]
        )
        await session.commit()

    # The table owner bypasses RLS; switch to a non-owner predefined role so the
    # policy is actually enforced.
    async with session_factory() as session:
        await session.execute(text("SET ROLE pg_read_all_data"))
        await session.execute(
            text("select set_config('app.tenant_id', :tenant_id, false)"),
            {"tenant_id": str(tenant_a.id)},
        )
        rows = list(
            await session.scalars(
                select(Customer).where(
                    Customer.external_customer_id.in_([external_a, external_b])
                )
            )
        )
        await session.execute(text("RESET ROLE"))

    assert [row.external_customer_id for row in rows] == [external_a]


@pytest.mark.asyncio
async def test_rls_rejects_cross_tenant_insert(
    session_factory,
    tenant_a,
    tenant_b,
) -> None:
    async with session_factory() as session:
        await session.execute(text("SET ROLE pg_write_all_data"))
        await session.execute(
            text("select set_config('app.tenant_id', :tenant_id, false)"),
            {"tenant_id": str(tenant_a.id)},
        )
        session.add(
            Customer(
                id=uuid4(),
                tenant_id=tenant_b.id,
                name="Cross Tenant Insert",
                external_customer_id=f"rls-cross-{uuid4().hex[:8]}",
                support_tier="standard",
                status="active",
            )
        )
        with pytest.raises(DBAPIError):
            await session.commit()
        await session.rollback()
        await session.execute(text("RESET ROLE"))
