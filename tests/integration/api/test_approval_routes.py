from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.database.models.support import ApprovalAction


def _high_risk_headers(api_headers: dict[str, str]) -> dict[str, str]:
    return {**api_headers, "X-Actor-Type": "service"}


def _create_high_risk_refund(api_client, payment, headers: dict[str, str]):
    thread_id = f"api-approval-{uuid4().hex}"
    response = api_client.post(
        "/api/v1/refunds",
        headers=headers,
        json={
            "thread_id": thread_id,
            "payment_id": str(payment.id),
            "amount": "20.00",
            "refund_idempotency_key": f"api-approval-{uuid4().hex}",
            "message": "需要人工审批的退款",
        },
    )
    assert response.status_code == 202
    return response.json()


@pytest.mark.asyncio
async def test_rejected_approval_route_persists_reason_and_status(
    authorized_api_client,
    session_factory,
    payment,
    api_headers,
):
    created = _create_high_risk_refund(authorized_api_client, payment, _high_risk_headers(api_headers))

    response = authorized_api_client.post(
        f"/api/v1/approvals/{created['approval_request_id']}",
        headers=api_headers,
        json={"thread_id": created["thread_id"], "approved": False, "reason": "证据不足"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    async with session_factory() as session:
        action = await session.scalar(
            select(ApprovalAction).where(
                ApprovalAction.approval_request_id == created["approval_request_id"],
                ApprovalAction.action == "rejected",
            )
        )
    assert action is not None
    assert action.reason == "证据不足"


@pytest.mark.asyncio
async def test_processed_approval_cannot_be_submitted_twice(authorized_api_client, payment, api_headers):
    created = _create_high_risk_refund(authorized_api_client, payment, _high_risk_headers(api_headers))
    approval_url = f"/api/v1/approvals/{created['approval_request_id']}"
    payload = {"thread_id": created["thread_id"], "approved": True, "reason": "证据充分"}

    first = authorized_api_client.post(approval_url, headers=api_headers, json=payload)
    second = authorized_api_client.post(approval_url, headers=api_headers, json=payload)

    assert first.status_code == 200
    assert first.json()["status"] == "approved_for_execution"
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "approval_not_pending"
