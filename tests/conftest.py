import asyncio
import os

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import get_settings
from backend.database.base import Base
from backend.database.session import get_session_factory
import backend.database.models  # noqa: F401

pytest_plugins = ("tests.integration.database.conftest",)


def _ensure_schema(url: str) -> None:
    async def run() -> None:
        engine = create_async_engine(url, pool_pre_ping=True)
        try:
            async with engine.begin() as connection:
                tables = await connection.run_sync(
                    lambda sync_connection: inspect(sync_connection).get_table_names()
                )
                if "tenants" not in tables:
                    await connection.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest.fixture
def database_url() -> str:
    url = get_settings().database_url
    _ensure_schema(url)
    return url


@pytest.fixture
def postgresql_test_url(database_url: str) -> str:
    return os.getenv("TEST_DATABASE_URL", database_url)


@pytest.fixture
def session_factory() -> async_sessionmaker[AsyncSession]:
    return get_session_factory()
