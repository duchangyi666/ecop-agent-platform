from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.database.models.governance import MemoryRecord


async def expire_memory_records(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        statement = select(MemoryRecord).where(
            MemoryRecord.ttl_expires_at <= now,
            MemoryRecord.deleted_at.is_(None),
        )
        expired = list(await session.scalars(statement))
        for record in expired:
            record.deleted_at = now
        await session.commit()
        return len(expired)


__all__ = ["expire_memory_records"]
