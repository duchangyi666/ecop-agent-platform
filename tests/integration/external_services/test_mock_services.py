from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from mock_services.app import create_mock_services_app
from mock_services.client import MockBillingClient
from mock_services.storage import (
    MockBillingStorage,
    MockCrmStorage,
    MockMonitoringStorage,
    MockNotificationStorage,
)


def test_mock_billing_preview_execute_and_idempotency() -> None:
    billing = MockBillingStorage()
    payment_id = uuid4()
    billing.add_payment(payment_id=payment_id, customer_id=uuid4(), amount=Decimal("88.00"))
    app = create_mock_services_app(billing_storage=billing)

    with TestClient(app) as client:
        preview = client.post(
            "/billing/refunds/preview",
            json={
                "payment_id": str(payment_id),
                "amount": "88.00",
                "idempotency_key": "refund-001",
            },
        )
        first = client.post(
            "/billing/refunds",
            json={
                "payment_id": str(payment_id),
                "amount": "88.00",
                "idempotency_key": "refund-001",
            },
        )
        second = client.post(
            "/billing/refunds",
            json={
                "payment_id": str(payment_id),
                "amount": "88.00",
                "idempotency_key": "refund-001",
            },
        )
        by_key = client.get("/billing/refunds/refund-001")

    assert preview.status_code == 200
    assert preview.json()["status"] == "previewed"
    assert first.status_code == 201
    assert first.json()["status"] == "succeeded"
    assert second.status_code == 200
    assert second.json()["refund_id"] == first.json()["refund_id"]
    assert by_key.json()["idempotency_key"] == "refund-001"


def test_mock_crm_monitoring_notification_endpoints() -> None:
    crm = MockCrmStorage()
    customer_id = uuid4()
    crm.add_customer(customer_id=customer_id, name="Acme", support_tier="gold")
    app = create_mock_services_app(
        crm_storage=crm,
        monitoring_storage=MockMonitoringStorage(),
        notification_storage=MockNotificationStorage(),
    )

    with TestClient(app) as client:
        customer = client.get(f"/crm/customers/{customer_id}")
        incident = client.post(
            "/monitoring/incidents",
            json={"service": "api", "severity": "major", "summary": "API latency elevated"},
        )
        notification = client.post(
            "/notification/notifications",
            json={"recipient": "admin@example.com", "channel": "email", "message": "Incident opened"},
        )

    assert customer.status_code == 200
    assert customer.json()["support_tier"] == "gold"
    assert incident.status_code == 201
    assert notification.status_code == 202


@pytest.mark.asyncio
async def test_mock_billing_client_uses_http_boundary() -> None:
    billing = MockBillingStorage()
    payment_id = uuid4()
    billing.add_payment(payment_id=payment_id, customer_id=uuid4(), amount=Decimal("20.00"))
    app = create_mock_services_app(billing_storage=billing)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        client = MockBillingClient("http://test", client=http_client)
        preview = await client.preview_refund(
            payment_id=payment_id,
            amount=Decimal("20.00"),
            idempotency_key="client-001",
        )
        executed = await client.execute_refund(
            payment_id=payment_id,
            amount=Decimal("20.00"),
            idempotency_key="client-001",
        )

    assert preview["status"] == "previewed"
    assert executed["status"] == "succeeded"
