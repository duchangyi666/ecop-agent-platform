from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.database.models.billing import CustomerContact
from backend.database.models.identity import Permission, User, UserRole


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


@pytest.mark.asyncio
async def test_ticket_read_respects_customer_association_and_internal_visibility(
    ticket_ops_api_client, api_headers, tenant_a, tenant_a_user, customer_id, session_factory,
):
    created = ticket_ops_api_client.post("/api/v1/tickets", headers=api_headers, json=_payload(customer_id, "scope"))
    assert created.status_code == 201, created.text
    ticket_id = created.json()["ticket_id"]
    other_id = uuid4()
    async with session_factory() as session:
        session.add(User(id=other_id, tenant_id=tenant_a.id, email=f"{other_id}@example.com", display_name="customer", status="active"))
        read_role = await session.scalar(select(Permission.role_id).where(
            Permission.tenant_id == tenant_a.id, Permission.code == "ticket.read"
        ))
        session.add(UserRole(tenant_id=tenant_a.id, user_id=other_id, role_id=read_role))
        await session.commit()
    headers = {**api_headers, "X-Actor-Id": str(other_id)}
    url = f"/api/v1/tickets/{ticket_id}"
    assert ticket_ops_api_client.get(url, headers=headers).status_code == 404
    assert ticket_ops_api_client.get("/api/v1/tickets", headers=headers).json()["tickets"] == []
    async with session_factory() as session:
        session.add(CustomerContact(tenant_id=tenant_a.id, customer_id=customer_id, user_id=other_id,
                                    channel="email", masked_value="test", contact_hash=uuid4().hex,
                                    preferred_language="zh"))
        await session.commit()
    owner_view = ticket_ops_api_client.get(url, headers=headers)
    assert owner_view.status_code == 200
    assert owner_view.json()["messages"] == []
    assert owner_view.json()["events"] == []
    assert any(item["ticket_id"] == ticket_id for item in ticket_ops_api_client.get("/api/v1/tickets", headers=headers).json()["tickets"])
    staff_view = ticket_ops_api_client.get(url, headers=api_headers).json()
    assert staff_view["messages"] and staff_view["events"]
