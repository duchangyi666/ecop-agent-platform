from __future__ import annotations

from uuid import UUID
from datetime import datetime, timezone
from math import log

from sqlalchemy import select, func, update
from backend.agent.guards import InputSecurityGuard

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

    async def recall(self, *, scope: TenantScope, limit: int = 3) -> list[str]:
        """Recall private preferences. updated_at is the last activity timestamp.

        Creation and expiry remain unchanged; retrieval never renews hard TTL.
        """
        if self.session_factory is None or scope.actor_id is None:
            return []
        limit = max(0, min(limit, 5))
        if limit == 0:
            return []
        now = datetime.now(timezone.utc)
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            age_days = func.greatest(0, func.extract("epoch", now - MemoryRecord.updated_at) / 86400.0)
            score = MemoryRecord.confidence * func.exp(-log(2) * age_days / 30.0)
            rows = list(await uow.session.scalars(select(MemoryRecord).where(
                MemoryRecord.tenant_id == scope.tenant_id,
                MemoryRecord.user_id == scope.actor_id,
                MemoryRecord.deleted_at.is_(None),
                MemoryRecord.ttl_expires_at > now,
                MemoryRecord.memory_type.in_(["language_preference", "timezone_preference", "user_preference"]),
                MemoryRecord.confidence >= self.policy.min_confidence,
            ).order_by(score.desc(), MemoryRecord.id).limit(20)))
            chosen = []
            contents = []
            guard = InputSecurityGuard()
            for row in rows:
                content = row.payload_summary.get("content")
                if not isinstance(content, str) or content in contents:
                    continue
                from backend.memory.candidates import MemoryCandidate
                candidate = MemoryCandidate(row.memory_type, content, row.confidence, 1)
                if not self.policy.allow(candidate) or guard.evaluate(content).status != "allow":
                    continue
                chosen.append(row.id)
                contents.append(content)
                if len(contents) >= limit:
                    break
            if chosen:
                await uow.session.execute(update(MemoryRecord).where(
                    MemoryRecord.tenant_id == scope.tenant_id,
                    MemoryRecord.user_id == scope.actor_id,
                    MemoryRecord.id.in_(chosen),
                ).values(updated_at=func.greatest(MemoryRecord.updated_at, now)))
            return contents

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
