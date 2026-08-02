from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.database.models.identity import User
from backend.database.models.support import ApprovalRequest
from backend.domain.approval import ApprovalStatus


def _refund_payload(payment, prefix: str) -> dict[str, str]:
    return {
        "thread_id": f"permission-{prefix}-{uuid4().hex}",
        "payment_id": str(payment.id),
        "amount": "20.00",
        "refund_idempotency_key": f"permission-{prefix}-{uuid4().hex}",
        "message": "权限安全测试",
    }


@pytest.mark.asyncio
async def test_inactive_permission_is_not_authorized(api_client, grant_permission, tenant_a_user, payment, api_headers):
    await grant_permission(tenant_a_user.id, "refund.request", permission_status="inactive")

    response = api_client.post("/api/v1/refunds", headers=api_headers, json=_refund_payload(payment, "inactive-permission"))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.asyncio
async def test_inactive_user_cannot_submit_refund(
    authorized_api_client,
    payment,
    tenant_a_user,
    api_headers,
    session_factory,
):
    async with session_factory() as session:
        user = await session.get(User, tenant_a_user.id)
        user.status = "inactive"
        await session.commit()

    response = authorized_api_client.post("/api/v1/refunds", headers=api_headers, json=_refund_payload(payment, "inactive-user"))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "tenant_identity_invalid"


@pytest.mark.asyncio
async def test_request_only_user_cannot_process_approval(
    request_only_api_client,
    payment,
    api_headers,
    session_factory,
):
    create_response = request_only_api_client.post(
        "/api/v1/refunds",
        headers={**api_headers, "X-Actor-Type": "service"},
        json=_refund_payload(payment, "approval"),
    )
    assert create_response.status_code == 202
    created = create_response.json()

    response = request_only_api_client.post(
        f"/api/v1/approvals/{created['approval_request_id']}",
        headers=api_headers,
        json={"thread_id": created["thread_id"], "approved": False, "reason": "没有审批权限"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
    async with session_factory() as session:
        approval = await session.scalar(
            select(ApprovalRequest).where(ApprovalRequest.id == created["approval_request_id"])
        )
    assert approval is not None and approval.status is ApprovalStatus.PENDING
