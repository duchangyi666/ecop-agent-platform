from __future__ import annotations

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

pytest_plugins = ("tests.integration.database.conftest",)


@pytest_asyncio.fixture
async def session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, pool_pre_ping=True, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def api_client(database_url: str, session_factory):
    from backend.api.dependencies import get_database_url, get_session_factory_dependency
    from backend.main import create_app

    app = create_app()
    app.dependency_overrides[get_database_url] = lambda: database_url
    app.dependency_overrides[get_session_factory_dependency] = lambda: session_factory
    with TestClient(app) as client:
        yield client


@pytest_asyncio.fixture
async def api_headers(tenant_a, tenant_a_user) -> dict[str, str]:
    return {
        "X-Tenant-Id": str(tenant_a.id),
        "X-Actor-Id": str(tenant_a_user.id),
        "X-Actor-Type": "user",
    }
