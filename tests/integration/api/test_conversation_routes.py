from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.database.models.billing import CustomerContact
from backend.database.models.identity import Permission, User, UserRole


@pytest_asyncio.fixture
async def customer_contact(session_factory, tenant_a, tenant_a_user, customer_id):
    async with session_factory() as session:
        session.add(CustomerContact(tenant_id=tenant_a.id, customer_id=customer_id, user_id=tenant_a_user.id,
                                    channel="email", masked_value="test", contact_hash=uuid4().hex,
                                    preferred_language="zh"))
        await session.commit()


def _payload(customer_id, prefix: str) -> dict[str, str]:
    return {
        "customer_id": str(customer_id),
        "channel": "customer_portal",
        "subject": f"会话 {prefix}",
        "initial_message": "请帮我查看账单",
    }


@pytest.mark.asyncio
async def test_conversation_route_creates_and_returns_detail(
    conversation_api_client,
    api_headers,
    customer_id,
    customer_contact,
) -> None:
    response = conversation_api_client.post(
        "/api/v1/conversations",
        headers=api_headers,
        json=_payload(customer_id, "ok"),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["conversation"]["status"] == "open"
    assert body["conversation"]["message_count"] == 1
    assert body["messages"][0]["role"] == "user"


@pytest.mark.asyncio
async def test_conversation_route_requires_permission(api_client, api_headers, customer_id) -> None:
    response = api_client.post(
        "/api/v1/conversations",
        headers=api_headers,
        json=_payload(customer_id, "forbidden"),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.asyncio
async def test_conversation_route_lists_and_appends_message(
    conversation_api_client,
    api_headers,
    customer_id,
    customer_contact,
) -> None:
    created = conversation_api_client.post(
        "/api/v1/conversations",
        headers=api_headers,
        json=_payload(customer_id, "list"),
    ).json()
    conversation_id = created["conversation"]["conversation_id"]

    list_response = conversation_api_client.get("/api/v1/conversations", headers=api_headers)
    assert list_response.status_code == 200
    assert len(list_response.json()["conversations"]) >= 1

    message_response = conversation_api_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=api_headers,
        json={
            "role": "user",
            "body": "补充一句：这是重复扣款",
            "visibility": "public",
        },
    )
    assert message_response.status_code == 201, message_response.text
    assert message_response.json()["conversation"]["message_count"] == 2

    detail_response = conversation_api_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=api_headers,
    )
    assert detail_response.status_code == 200
    assert len(detail_response.json()["messages"]) == 2


@pytest.mark.asyncio
async def test_conversation_route_requires_target_identity(
    conversation_api_client,
    api_headers,
) -> None:
    response = conversation_api_client.post(
        "/api/v1/conversations",
        headers=api_headers,
        json={
            "channel": "chat",
            "subject": f"无主体 {uuid4().hex[:8]}",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_conversation_target"


@pytest.mark.asyncio
async def test_conversation_access_is_scoped_and_staff_requires_explicit_permissions(
    conversation_api_client, api_headers, tenant_a, tenant_a_user, customer_id, customer_contact,
    session_factory, grant_permission,
):
    created = conversation_api_client.post("/api/v1/conversations", headers=api_headers, json=_payload(customer_id, "private"))
    assert created.status_code == 201, created.text
    conversation_id = created.json()["conversation"]["conversation_id"]
    other_id = uuid4()
    async with session_factory() as session:
        session.add(User(id=other_id, tenant_id=tenant_a.id, email=f"{other_id}@example.com", display_name="other", status="active"))
        roles = (await session.scalars(select(Permission.role_id).where(Permission.tenant_id == tenant_a.id,
                 Permission.code.in_(["conversation.create", "conversation.read", "conversation.write"])))).all()
        for role_id in roles:
            session.add(UserRole(tenant_id=tenant_a.id, user_id=other_id, role_id=role_id))
        await session.commit()
    other_headers = {**api_headers, "X-Actor-Id": str(other_id)}
    url = f"/api/v1/conversations/{conversation_id}"
    assert conversation_api_client.get(url, headers=other_headers).status_code == 404
    assert not conversation_api_client.get("/api/v1/conversations", headers=other_headers).json()["conversations"]
    assert conversation_api_client.post(url + "/messages", headers=other_headers, json={"body": "intrusion"}).status_code == 404
    assert conversation_api_client.post("/api/v1/conversations", headers=other_headers, json=_payload(customer_id, "spoof")).status_code == 403
    assert conversation_api_client.post("/api/v1/conversations", headers=other_headers, json={"user_id": str(tenant_a_user.id), "subject": "spoof"}).status_code == 403
    assert conversation_api_client.post(url + "/messages", headers=api_headers, json={"body": "fake", "role": "system"}).status_code == 403
    await grant_permission(other_id, "conversation.write.all")
    assert conversation_api_client.post(url + "/messages", headers=other_headers, json={"body": "no read access"}).status_code == 403
    await grant_permission(other_id, "conversation.read.all")
    response = conversation_api_client.post(url + "/messages", headers=other_headers, json={"body": "internal", "role": "agent", "visibility": "internal"})
    assert response.status_code == 201, response.text
    assert len(response.json()["messages"]) == 2
    assert len(conversation_api_client.get(url, headers=other_headers).json()["messages"]) == 2
    owner_view = conversation_api_client.get(url, headers=api_headers).json()
    assert len(owner_view["messages"]) == owner_view["conversation"]["message_count"] == 1
    assert conversation_api_client.get("/api/v1/conversations", headers=api_headers).json()["conversations"][0]["message_count"] == 1
