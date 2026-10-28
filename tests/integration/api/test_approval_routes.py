from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.database.models.governance import WorkflowCheckpoint
from backend.database.models.support import ApprovalAction, ApprovalRequest
from backend.domain.approval import ApprovalStatus


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


@pytest.mark.asyncio
async def test_approval_cannot_resume_another_refund_workflow(
    authorized_api_client, payment, api_headers, session_factory,
):
    first = _create_high_risk_refund(authorized_api_client, payment, _high_risk_headers(api_headers))
    second = _create_high_risk_refund(authorized_api_client, payment, _high_risk_headers(api_headers))
    response = authorized_api_client.post(
        f"/api/v1/approvals/{first['approval_request_id']}",
        headers=api_headers,
        json={"thread_id": second["thread_id"], "approved": True, "reason": "incorrect workflow"},
    )
    assert response.status_code == 422
    async with session_factory() as session:
        for created in (first, second):
            approval = await session.get(ApprovalRequest, created["approval_request_id"])
            assert approval.status is ApprovalStatus.PENDING
            actions = list(await session.scalars(
                select(ApprovalAction).where(
                    ApprovalAction.approval_request_id == approval.id,
                )
            ))
            assert actions == []
            checkpoint = await session.scalar(
                select(WorkflowCheckpoint).where(WorkflowCheckpoint.thread_id == created["thread_id"])
            )
            assert checkpoint.status == "awaiting_approval"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["approval_request_id", "refund_id"])
async def test_approval_rejects_inconsistent_checkpoint(
    authorized_api_client, payment, api_headers, session_factory, field,
):
    created = _create_high_risk_refund(authorized_api_client, payment, _high_risk_headers(api_headers))
    async with session_factory() as session:
        checkpoint = await session.scalar(
            select(WorkflowCheckpoint).where(WorkflowCheckpoint.thread_id == created["thread_id"])
        )
        checkpoint.state_summary = {**checkpoint.state_summary, field: str(uuid4())}
        await session.commit()

    response = authorized_api_client.post(
        f"/api/v1/approvals/{created['approval_request_id']}",
        headers=api_headers,
        json={"thread_id": created["thread_id"], "approved": True, "reason": "invalid checkpoint"},
    )
    assert response.status_code == 422
    async with session_factory() as session:
        approval = await session.get(ApprovalRequest, created["approval_request_id"])
        assert approval.status is ApprovalStatus.PENDING
        assert not list(await session.scalars(
            select(ApprovalAction).where(ApprovalAction.approval_request_id == approval.id)
        ))


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [True, False])
async def test_expired_refund_approval_rejects_decisions(
    authorized_api_client, payment, api_headers, session_factory, approved,
):
    created = _create_high_risk_refund(authorized_api_client, payment, _high_risk_headers(api_headers))
    async with session_factory() as session:
        approval = await session.get(ApprovalRequest, created["approval_request_id"])
        approval.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    response = authorized_api_client.post(
        f"/api/v1/approvals/{created['approval_request_id']}", headers=api_headers,
        json={"thread_id": created["thread_id"], "approved": approved, "reason": "expired"},
    )
    assert response.status_code == 422
    async with session_factory() as session:
        approval = await session.get(ApprovalRequest, created["approval_request_id"])
        assert approval.status is ApprovalStatus.PENDING
        assert not list(await session.scalars(
            select(ApprovalAction).where(ApprovalAction.approval_request_id == approval.id)
        ))
        checkpoint = await session.scalar(
            select(WorkflowCheckpoint).where(WorkflowCheckpoint.thread_id == created["thread_id"])
        )
        assert checkpoint.status == "awaiting_approval"
