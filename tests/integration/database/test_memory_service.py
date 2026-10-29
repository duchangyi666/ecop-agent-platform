from __future__ import annotations

import pytest
from sqlalchemy import select

from backend.database.base import TenantScope
from backend.database.models.governance import MemoryRecord
from backend.memory.service import MemoryService


@pytest.mark.asyncio
async def test_memory_service_persists_extracted_preference(
    session_factory,
    tenant_a,
    tenant_a_user,
) -> None:
    scope = TenantScope(tenant_id=tenant_a.id)
    service = MemoryService(session_factory)

    records = await service.capture(
        scope=scope,
        user_id=tenant_a_user.id,
        customer_id=None,
        message="客户咨询，我偏好使用中文沟通",
        response="已记录偏好。",
    )

    assert records
    assert any(record.memory_type == "language_preference" for record in records)

    async with session_factory() as session:
        persisted = list(
            await session.scalars(
                select(MemoryRecord).where(
                    MemoryRecord.tenant_id == tenant_a.id,
                    MemoryRecord.deleted_at.is_(None),
                )
            )
        )
    assert len(persisted) == len(records)
    assert all("sk-" not in record.payload_summary.get("content", "") for record in persisted)


@pytest.mark.asyncio
async def test_recall_decays_refreshes_and_isolates(session_factory, tenant_a, tenant_a_user):
    from datetime import datetime, timezone, timedelta
    from uuid import uuid4
    now = datetime.now(timezone.utc)
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id)
    ids = []
    async with session_factory() as session:
        for content, age, expired, owner in [
            ("preference=recent", 1, False, tenant_a_user.id),
            ("preference=old", 60, False, tenant_a_user.id),
            ("preference=expired", 0, True, tenant_a_user.id),
            ("preference=tenant shared", 0, False, None),
        ]:
            row = MemoryRecord(id=uuid4(), tenant_id=tenant_a.id, user_id=owner,
                memory_type="user_preference", payload_summary={"content": content},
                payload_hash=uuid4().hex, source="conversation", confidence=0.8,
                created_at=now-timedelta(days=age), updated_at=now-timedelta(days=age),
                ttl_expires_at=now+timedelta(days=-1 if expired else 90))
            session.add(row)
            ids.append(row.id)
        await session.commit()
    service = MemoryService(session_factory)
    assert await service.recall(scope=scope, limit=1) == ["preference=recent"]
    async with session_factory() as session:
        recent = await session.get(MemoryRecord, ids[0])
        old = await session.get(MemoryRecord, ids[1])
        assert recent.updated_at >= now
        assert recent.created_at < now
        assert recent.ttl_expires_at == now+timedelta(days=90)
        assert old.updated_at == now-timedelta(days=60)
    assert set(await service.recall(scope=scope)) == {"preference=recent", "preference=old"}
    assert await service.recall(scope=TenantScope(tenant_id=tenant_a.id)) == []
