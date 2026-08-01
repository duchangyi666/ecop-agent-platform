from unittest.mock import AsyncMock, Mock

import pytest

from backend.database.unit_of_work import UnitOfWork


@pytest.mark.asyncio
async def test_unit_of_work_exposes_repositories_and_commits() -> None:
    session = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    factory = Mock()
    uow = UnitOfWork(factory, session=session)

    async with uow as active:
        assert active.identity.session is session
        assert active.billing.session is session
        assert active.support.session is session
        assert active.governance.session is session

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    session.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_and_closes_owned_session() -> None:
    session = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    factory = Mock(return_value=session)
    uow = UnitOfWork(factory)

    with pytest.raises(RuntimeError):
        async with uow:
            raise RuntimeError("force rollback")

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()
