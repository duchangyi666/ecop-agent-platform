from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.database.models.governance import MemoryRecord
from backend.database.models.identity import Tenant
from backend.database.tenant_context import set_tenant_context


async def expire_memory_records(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    now = datetime.now(timezone.utc)
    total = 0
    async with session_factory() as session:
        tenant_ids = list(
            await session.scalars(
                select(Tenant.id).where(Tenant.deleted_at.is_(None))
            )
        )
        for tenant_id in tenant_ids:
            await set_tenant_context(session, tenant_id)
            statement = select(MemoryRecord).where(
                MemoryRecord.ttl_expires_at <= now,
                MemoryRecord.deleted_at.is_(None),
            )
            expired = list(await session.scalars(statement))
            for record in expired:
                record.deleted_at = now
            await session.commit()
            total += len(expired)
        return total


__all__ = ["expire_memory_records"]
