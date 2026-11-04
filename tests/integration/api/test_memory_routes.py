from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.database.base import TenantScope
from backend.database.models.governance import MemoryRecord
from backend.database.models.identity import User, UserRole, Permission
from backend.memory.service import MemoryService


@pytest.mark.asyncio
async def test_memory_management_is_private_and_delete_removes_recall(
    customer_consult_api_client, api_headers, session_factory, tenant_a, tenant_a_user,
):
    now = datetime.now(timezone.utc)
    old = now-timedelta(days=3)
    other_id = uuid4()
    ids = [uuid4() for _ in range(3)]
    async with session_factory() as session:
        session.add(User(id=other_id, tenant_id=tenant_a.id, email=f"{other_id}@example.com",
                         display_name="other", status="active"))
        role_id = await session.scalar(select(Permission.role_id).where(
            Permission.tenant_id == tenant_a.id, Permission.code == "customer.consult",
        ))
        session.add(UserRole(tenant_id=tenant_a.id, user_id=other_id, role_id=role_id))
        for memory_id, owner, expired in [(ids[0], tenant_a_user.id, False),
                                          (ids[1], other_id, False),
                                          (ids[2], tenant_a_user.id, True)]:
            session.add(MemoryRecord(id=memory_id, tenant_id=tenant_a.id, user_id=owner,
                memory_type="user_preference", payload_summary={"content": "preference=email"},
                payload_hash=uuid4().hex, source="conversation", confidence=0.8,
                created_at=old, updated_at=old,
                ttl_expires_at=old if expired else now+timedelta(days=30)))
        await session.commit()
    client = customer_consult_api_client
    response = client.get("/api/v1/memories", headers=api_headers)
    assert response.status_code == 200, response.text
    assert [item["memory_id"] for item in response.json()["memories"]] == [str(ids[0])]
    async with session_factory() as session:
        assert (await session.get(MemoryRecord, ids[0])).updated_at == old
    other_headers = {**api_headers, "X-Actor-Id": str(other_id)}
    assert client.delete(f"/api/v1/memories/{ids[0]}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/v1/memories/{ids[1]}", headers=api_headers).status_code == 404
    assert client.patch(f"/api/v1/memories/{ids[1]}", headers=api_headers, json={"value": "other"}).status_code == 404
    assert client.delete(f"/api/v1/memories/{ids[0]}", headers=api_headers).status_code == 204
    assert client.delete(f"/api/v1/memories/{ids[0]}", headers=api_headers).status_code == 404
    assert client.get("/api/v1/memories", headers=api_headers).json()["memories"] == []
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id)
    assert await MemoryService(session_factory).recall(scope=scope) == []


@pytest.mark.asyncio
async def test_memory_management_requires_permission(api_client, api_headers):
    assert api_client.get("/api/v1/memories", headers=api_headers).status_code == 403
    assert api_client.delete(f"/api/v1/memories/{uuid4()}", headers=api_headers).status_code == 403


@pytest.mark.asyncio
async def test_memory_correction_validates_value_and_replaces_recall(
    customer_consult_api_client, api_headers, session_factory, tenant_a, tenant_a_user,
):
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id)
    service = MemoryService(session_factory)
    records = await service.capture(scope=scope, user_id=tenant_a_user.id,
                                    customer_id=None, message="使用中文")
    memory_id = records[0].id
    client = customer_consult_api_client
    url = f"/api/v1/memories/{memory_id}"
    rejected = client.patch(url, headers=api_headers, json={"value": "unknown"})
    assert rejected.status_code == 422
    assert await service.recall(scope=scope) == ["preferred_language=zh"]
    corrected = client.patch(url, headers=api_headers, json={"value": "en"})
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["memory_id"] != str(memory_id)
    assert corrected.json()["content"] == "preferred_language=en"
    assert await service.recall(scope=scope) == ["preferred_language=en"]
    assert client.patch(url, headers=api_headers, json={"value": "zh"}).status_code == 404
    async with session_factory() as session:
        original = await session.get(MemoryRecord, memory_id)
        assert original.deleted_at is not None


@pytest.mark.asyncio
async def test_memory_disable_stops_capture_recall_and_refresh(
    customer_consult_api_client, api_headers, session_factory, tenant_a, tenant_a_user,
):
    from backend.database.unit_of_work import UnitOfWork
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id)
    service = MemoryService(session_factory)
    rows = await service.capture(scope=scope, user_id=tenant_a_user.id, customer_id=None, message="使用中文")
    previous = rows[0].updated_at
    client = customer_consult_api_client
    url = "/api/v1/memories/settings/current"
    assert client.patch(url, headers=api_headers, json={"enabled": False}).json() == {"enabled": False}
    assert client.get(url, headers=api_headers).json() == {"enabled": False}
    assert await service.recall(scope=scope) == []
    assert await service.capture(scope=scope, user_id=tenant_a_user.id, customer_id=None, message="使用英文") == []
    assert client.patch(f"/api/v1/memories/{rows[0].id}", headers=api_headers, json={"value": "en"}).status_code == 409
    async with UnitOfWork(session_factory, scope=scope) as uow:
        await service.mark_used_in_uow(uow, scope=scope, contents=["preferred_language=zh"])
    async with session_factory() as session:
        assert (await session.get(MemoryRecord, rows[0].id)).updated_at == previous
    assert len(client.get("/api/v1/memories", headers=api_headers).json()["memories"]) == 1
    assert client.patch(url, headers=api_headers, json={"enabled": True}).status_code == 200
    assert await service.recall(scope=scope) == ["preferred_language=zh"]


@pytest.mark.asyncio
async def test_memory_list_paginates_without_duplicate_records(
    customer_consult_api_client, api_headers, session_factory, tenant_a, tenant_a_user,
):
    service = MemoryService(session_factory)
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id)
    for text in ("我偏好邮件", "我偏好短信", "我偏好电话"):
        await service.capture(scope=scope, user_id=tenant_a_user.id, customer_id=None, message=text)
    client = customer_consult_api_client
    first = client.get("/api/v1/memories?limit=2", headers=api_headers).json()
    second = client.get(f"/api/v1/memories?limit=2&offset={first['next_offset']}", headers=api_headers).json()
    assert len(first["memories"]) == 2
    assert len(second["memories"]) == 1
    assert second["next_offset"] is None
    assert len({row["memory_id"] for row in first["memories"]+second["memories"]}) == 3
