from __future__ import annotations

from uuid import uuid4

import pytest


def _payload(customer_id, prefix: str) -> dict[str, str]:
    return {
        "thread_id": f"api-ticket-ops-{prefix}-{uuid4().hex}",
        "customer_id": str(customer_id),
        "subject": "登录问题",
        "priority": "high",
        "description_summary": "用户无法登录",
        "message": "请创建工单",
    }


@pytest.mark.asyncio
async def test_ticket_ops_route_lists_and_returns_detail(
    ticket_ops_api_client,
    api_headers,
    customer_id,
) -> None:
    created = ticket_ops_api_client.post(
        "/api/v1/tickets",
        headers=api_headers,
        json=_payload(customer_id, "detail"),
    ).json()
    ticket_id = created["ticket_id"]

    list_response = ticket_ops_api_client.get("/api/v1/tickets", headers=api_headers)
    assert list_response.status_code == 200, list_response.text
    assert any(item["ticket_id"] == ticket_id for item in list_response.json()["tickets"])

    detail_response = ticket_ops_api_client.get(
        f"/api/v1/tickets/{ticket_id}",
        headers=api_headers,
    )
    assert detail_response.status_code == 200, detail_response.text
    assert detail_response.json()["ticket"]["status"] == "open"
    assert len(detail_response.json()["events"]) >= 1


@pytest.mark.asyncio
async def test_ticket_ops_route_patches_status_and_note(
    ticket_ops_api_client,
    api_headers,
    customer_id,
) -> None:
    created = ticket_ops_api_client.post(
        "/api/v1/tickets",
        headers=api_headers,
        json=_payload(customer_id, "patch"),
    ).json()
    ticket_id = created["ticket_id"]

    patch_response = ticket_ops_api_client.patch(
        f"/api/v1/tickets/{ticket_id}",
        headers=api_headers,
        json={
            "status": "resolved",
            "note": "客服已完成处理",
            "priority": "medium",
        },
    )

    assert patch_response.status_code == 200, patch_response.text
    body = patch_response.json()
    assert body["ticket"]["status"] == "resolved"
    assert body["ticket"]["priority"] == "medium"
    assert any(message["body"] == "客服已完成处理" for message in body["messages"])


@pytest.mark.asyncio
async def test_ticket_read_route_requires_permission(api_client, api_headers, customer_id) -> None:
    response = api_client.get("/api/v1/tickets", headers=api_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
