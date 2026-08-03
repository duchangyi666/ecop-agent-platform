import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import get_settings
from backend.database.session import get_session_factory

pytest_plugins = ("tests.integration.database.conftest",)


@pytest.fixture
def database_url() -> str:
    return get_settings().database_url


@pytest.fixture
def postgresql_test_url(database_url: str) -> str:
    return os.getenv("TEST_DATABASE_URL", database_url)


@pytest.fixture
def session_factory() -> async_sessionmaker[AsyncSession]:
    return get_session_factory()
