from __future__ import annotations

from uuid import UUID
from datetime import datetime, timezone, timedelta
from math import log

from sqlalchemy import select, func, update
from backend.agent.guards import InputSecurityGuard

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.database.base import TenantScope
from backend.database.models.governance import MemoryRecord
from backend.database.models.identity import User
from backend.domain.common import DomainError
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
        if candidates and user_id is not None:
            # Serialize even the first insert, when no memory row exists to lock.
            owner = await uow.session.scalar(select(User.id).where(
                User.tenant_id == scope.tenant_id, User.id == user_id,
                User.deleted_at.is_(None), User.status == "active",
            ).with_for_update())
            if owner is None:
                raise DomainError("memory owner not found in tenant scope")
        for candidate in candidates:
            if not self.policy.allow(candidate):
                continue
            if user_id is not None:
                now = datetime.now(timezone.utc)
                singleton = candidate.memory_type in {"language_preference", "timezone_preference"}
                statement = select(MemoryRecord).where(
                    MemoryRecord.tenant_id == scope.tenant_id,
                    MemoryRecord.user_id == user_id,
                    MemoryRecord.memory_type == candidate.memory_type,
                    MemoryRecord.deleted_at.is_(None),
                )
                if not singleton:
                    statement = statement.where(
                        MemoryRecord.payload_summary["content"].as_string() == candidate.content
                    )
                existing = list(await uow.session.scalars(statement.order_by(
                    MemoryRecord.updated_at.desc(), MemoryRecord.id,
                ).with_for_update()))
                reusable = next((row for row in existing
                    if row.payload_summary.get("content") == candidate.content
                    and row.ttl_expires_at > now), None)
                for row in existing:
                    if row is not reusable:
                        row.deleted_at = now
                if reusable is not None:
                    # Explicit repetition renews retention; passive recall does not.
                    reusable.updated_at = now
                    reusable.ttl_expires_at = now + timedelta(days=candidate.ttl_days)
                    records.append(reusable)
                    await uow.session.flush()
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
