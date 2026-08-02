from __future__ import annotations

from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_user_without_refund_request_permission_is_rejected(api_client, payment, api_headers):
    response = api_client.post(
        "/api/v1/refunds",
        headers=api_headers,
        json={
            "thread_id": f"auth-{uuid4().hex}",
            "payment_id": str(payment.id),
            "amount": "20.00",
            "refund_idempotency_key": f"auth-{uuid4().hex}",
            "message": "没有权限的退款申请",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
