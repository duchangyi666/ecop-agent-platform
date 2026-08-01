from __future__ import annotations

from datetime import timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database.base import Base

TEST_DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations"


@pytest.fixture
def metadata():
    from backend.database.models.identity import Tenant, User  # noqa: F401

    return Base.metadata


@pytest_asyncio.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    from backend.database.models.identity import Tenant, User  # noqa: F401

    engine = create_async_engine(TEST_DATABASE_URL, future=True)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        yield factory
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncSession:
    async with session_factory() as current_session:
        yield current_session
        await current_session.rollback()


@pytest_asyncio.fixture
async def tenant_a(session: AsyncSession):
    from backend.database.models.identity import Tenant

    tenant = Tenant(
        id=uuid4(),
        slug="tenant-a",
        name="Tenant A",
        status="active",
    )
    session.add(tenant)
    await session.commit()
    return tenant


@pytest_asyncio.fixture
async def tenant_b(session: AsyncSession):
    from backend.database.models.identity import Tenant

    tenant = Tenant(
        id=uuid4(),
        slug="tenant-b",
        name="Tenant B",
        status="active",
    )
    session.add(tenant)
    await session.commit()
    return tenant


@pytest_asyncio.fixture
async def user(session: AsyncSession, tenant_a):
    from backend.database.models.identity import User

    user = User(
        id=uuid4(),
        tenant_id=tenant_a.id,
        email="agent-a@example.com",
        display_name="Agent A",
        status="active",
        last_login_at=None,
    )
    session.add(user)
    await session.commit()
    return user
