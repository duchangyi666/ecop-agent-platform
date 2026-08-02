from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.database.base import TenantScope
from backend.database.models.governance import MemoryRecord
from backend.database.unit_of_work import UnitOfWork
from backend.memory.candidates import DeterministicMemoryExtractor
from backend.memory.policy import MemoryWritePolicy


class MemoryService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        *,
        extractor: DeterministicMemoryExtractor | None = None,
        policy: MemoryWritePolicy | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.extractor = extractor or DeterministicMemoryExtractor()
        self.policy = policy or MemoryWritePolicy()

    async def capture(
        self,
        *,
        scope: TenantScope,
        user_id: UUID | None,
        customer_id: UUID | None,
        message: str,
        response: str | None = None,
    ) -> list[MemoryRecord]:
        if self.session_factory is None:
            return []
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            return await self.capture_in_uow(
                uow,
                scope=scope,
                user_id=user_id,
                customer_id=customer_id,
                message=message,
                response=response,
            )

    async def capture_in_uow(
        self,
        uow: UnitOfWork,
        *,
        scope: TenantScope,
        user_id: UUID | None,
        customer_id: UUID | None,
        message: str,
        response: str | None = None,
    ) -> list[MemoryRecord]:
        candidates = self.extractor.extract(message=message, response=response)
        records: list[MemoryRecord] = []
        for candidate in candidates:
            if not self.policy.allow(candidate):
                continue
            record = await uow.governance.add_memory_candidate(
                scope=scope,
                user_id=user_id,
                customer_id=customer_id,
                payload={
                    "memory_type": candidate.memory_type,
                    "content": candidate.content,
                    "source": candidate.source,
                    "confidence": candidate.confidence,
                    "ttl_days": candidate.ttl_days,
                },
            )
            records.append(record)
        return records


__all__ = ["MemoryService"]
