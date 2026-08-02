from __future__ import annotations

from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_low_risk_refund_route_persists_refund(api_client, payment, api_headers):
    thread_id = f"api-{uuid4().hex}"
    response = api_client.post(
        "/api/v1/refunds",
        headers=api_headers,
        json={
            "thread_id": thread_id,
            "payment_id": str(payment.id),
            "amount": "20.00",
            "refund_idempotency_key": f"api-refund-{uuid4().hex}",
            "message": "重复扣费申请退款",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "refund_requested"
    assert response.json()["refund_id"] is not None


@pytest.mark.asyncio
async def test_missing_tenant_context_returns_structured_error(api_client):
    response = api_client.post("/api/v1/refunds", json={})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_tenant_context"


@pytest.mark.asyncio
async def test_cross_tenant_payment_is_rejected_by_http_boundary(api_client, payment, tenant_b, tenant_a_user):
    response = api_client.post(
        "/api/v1/refunds",
        headers={
            "X-Tenant-Id": str(tenant_b.id),
            "X-Actor-Id": str(tenant_a_user.id),
            "X-Actor-Type": "user",
        },
        json={
            "thread_id": f"api-cross-{uuid4().hex}",
            "payment_id": str(payment.id),
            "amount": "20.00",
            "refund_idempotency_key": f"api-cross-{uuid4().hex}",
            "message": "跨租户退款请求",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "business_rule_rejected"


@pytest.mark.asyncio
async def test_workflow_status_hides_raw_checkpoint_state(api_client, payment, api_headers):
    thread_id = f"api-status-{uuid4().hex}"
    create_response = api_client.post(
        "/api/v1/refunds",
        headers=api_headers,
        json={
            "thread_id": thread_id,
            "payment_id": str(payment.id),
            "amount": "20.00",
            "refund_idempotency_key": f"api-status-{uuid4().hex}",
            "message": "查询退款进度",
        },
    )
    assert create_response.status_code == 200

    response = api_client.get(f"/api/v1/workflows/{thread_id}", headers=api_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"] == thread_id
    assert body["has_refund_idempotency_key"] is True
    assert "state" not in body
    assert "refund_idempotency_key" not in body
