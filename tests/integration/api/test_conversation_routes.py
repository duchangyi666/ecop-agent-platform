from __future__ import annotations

from uuid import uuid4

import pytest


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
