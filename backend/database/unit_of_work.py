from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.database.base import TenantScope
from backend.database.repositories.billing import BillingRepository
from backend.database.repositories.evaluation import EvaluationRepository
from backend.database.repositories.governance import GovernanceRepository
from backend.database.repositories.identity import IdentityRepository
from backend.database.repositories.knowledge import KnowledgeRepository
from backend.database.repositories.support import SupportRepository


class UnitOfWork:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        scope: TenantScope | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.scope = scope
        self.session = session or session_factory()
        self._owns_session = session is None
        self.identity = IdentityRepository(self.session)
        self.billing = BillingRepository(self.session)
        self.support = SupportRepository(self.session)
        self.governance = GovernanceRepository(self.session)
        self.knowledge = KnowledgeRepository(self.session)
        self.evaluation = EvaluationRepository(self.session)

    async def __aenter__(self) -> "UnitOfWork":
        return self

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                await self.commit()
            else:
                await self.rollback()
        finally:
            if self._owns_session and self.session is not None:
                await self.session.close()
