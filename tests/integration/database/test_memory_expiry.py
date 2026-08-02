from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.database.base import TenantScope
from backend.database.models.governance import MemoryRecord
from backend.database.repositories.governance import GovernanceRepository
from backend.tasks.maintenance import expire_memory_records


@pytest.mark.asyncio
async def test_expire_memory_records_soft_deletes_expired_ttl(
    session_factory,
    tenant_a,
) -> None:
    scope = TenantScope(tenant_id=tenant_a.id)
    async with session_factory() as session:
        repository = GovernanceRepository(session)
        record = await repository.add_memory_candidate(
            scope=scope,
            user_id=None,
            customer_id=None,
            payload={
                "memory_type": "user_preference",
                "content": "preference=中文",
                "source": "conversation",
                "confidence": 0.9,
                "ttl_days": -1,
            },
        )
        await session.commit()
        record_id = record.id

    expired = await expire_memory_records(session_factory)

    assert expired == 1
    async with session_factory() as session:
        stored = await session.get(MemoryRecord, record_id)
    assert stored is not None
    assert stored.deleted_at is not None
    assert stored.deleted_at <= datetime.now(timezone.utc)
