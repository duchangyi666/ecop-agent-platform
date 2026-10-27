from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database.models.billing import Customer
from backend.database.tenant_context import set_tenant_context


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
async def test_rls_scope_does_not_leak_when_connection_is_reused(
    database_url, session_factory, tenant_a, tenant_b,
) -> None:
    external_a = f"pool-a-{uuid4().hex}"
    external_b = f"pool-b-{uuid4().hex}"
    async with session_factory() as session:
        session.add_all(
            [
                Customer(
                    tenant_id=tenant_a.id, name="Pool A", external_customer_id=external_a,
                    support_tier="standard", status="active",
                ),
                Customer(
                    tenant_id=tenant_b.id, name="Pool B", external_customer_id=external_b,
                    support_tier="standard", status="active",
                ),
            ]
        )
        await session.commit()

    engine = create_async_engine(database_url, pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    pids = []

    async def visible(tenant_id=None, *, rollback=False):
        async with factory() as session:
            await session.execute(text("SET LOCAL ROLE pg_read_all_data"))
            pids.append(await session.scalar(text("SELECT pg_backend_pid()")))
            if tenant_id is not None:
                await set_tenant_context(session, tenant_id)
            rows = list(await session.scalars(
                select(Customer.external_customer_id).where(
                    Customer.external_customer_id.in_([external_a, external_b])
                )
            ))
            if rollback:
                await session.rollback()
            else:
                await session.commit()
            return rows

    try:
        assert await visible(tenant_a.id) == [external_a]
        assert await visible() == []
        assert await visible(tenant_b.id, rollback=True) == [external_b]
        assert await visible() == []
        assert await visible(tenant_a.id) == [external_a]
        async with factory() as session:
            await session.execute(text("SET LOCAL ROLE pg_write_all_data"))
            pids.append(await session.scalar(text("SELECT pg_backend_pid()")))
            session.add(Customer(
                tenant_id=tenant_a.id, name="Denied", external_customer_id=f"denied-{uuid4().hex}",
                support_tier="standard", status="active",
            ))
            with pytest.raises(DBAPIError) as error:
                await session.flush()
            assert error.value.orig.sqlstate == "42501"
            await session.rollback()
        assert len(set(pids)) == 1
    finally:
        await engine.dispose()

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
