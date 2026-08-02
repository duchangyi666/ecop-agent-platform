from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.database.models.billing import Refund
from backend.database.models.support import ApprovalRequest
from backend.domain.billing import RefundStatus


@pytest.mark.asyncio
async def test_approval_read_route_lists_and_returns_detail(
    approval_read_api_client,
    api_headers,
    session_factory,
    tenant_a,
    tenant_a_user,
    payment,
) -> None:
    approval_id = uuid4()
    refund_id = uuid4()
    async with session_factory() as session:
        session.add(
            Refund(
                id=refund_id,
                tenant_id=tenant_a.id,
                payment_id=payment.id,
                amount=Decimal("88.00"),
                reason="重复扣费",
                status=RefundStatus.REQUESTED,
                idempotency_key=f"approval-read-{uuid4().hex}",
                requested_by_user_id=tenant_a_user.id,
            )
        )
        await session.flush()
        session.add(
            ApprovalRequest(
                id=approval_id,
                tenant_id=tenant_a.id,
                refund_id=refund_id,
                requested_by_user_id=tenant_a_user.id,
                action="refund.execute",
                payload_summary={"amount": "88.00"},
                payload_hash="test-hash",
                amount=Decimal("88.00"),
                risk_level="high",
                approval_role="finance_reviewer",
                status="pending",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                checkpoint_reference="thread-approval-read",
            )
        )
        await session.commit()

    list_response = approval_read_api_client.get("/api/v1/approvals", headers=api_headers)
    assert list_response.status_code == 200, list_response.text
    body = list_response.json()
    assert any(item["approval_request_id"] == str(approval_id) for item in body["approvals"])

    detail_response = approval_read_api_client.get(
        f"/api/v1/approvals/{approval_id}",
        headers=api_headers,
    )
    assert detail_response.status_code == 200, detail_response.text
    assert detail_response.json()["approval"]["status"] == "pending"
    assert detail_response.json()["approval"]["refund_id"] == str(refund_id)


@pytest.mark.asyncio
async def test_approval_read_route_requires_permission(api_client, api_headers) -> None:
    response = api_client.get("/api/v1/approvals", headers=api_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
