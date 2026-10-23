from __future__ import annotations

from datetime import timezone
import os
import uuid
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database.base import Base

# Never fall back to DATABASE_URL: these fixtures create and drop tables, and a
# missing TEST_DATABASE_URL must not be allowed to wipe a development database.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture
def metadata():
    import backend.database.models  # noqa: F401

    return Base.metadata


@pytest_asyncio.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    import backend.database.models  # noqa: F401

    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL must point to a dedicated test database")

    # Isolate each test session in a throwaway schema. Dropping that schema at
    # teardown is safe; the public schema (and any local demo data) is preserved.
    schema = f"test_{uuid.uuid4().hex[:12]}"
    engine = create_async_engine(
        TEST_DATABASE_URL,
        future=True,
        connect_args={"server_settings": {"search_path": f"{schema},public"}},
    )

    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        # checkfirst=False is required: SQLAlchemy would otherwise see the
        # public-schema tables and skip creating this session's isolated copy.
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection, checkfirst=False
            )
        )

    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        yield factory
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
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
