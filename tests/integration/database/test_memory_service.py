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
