from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4


@dataclass
class MockBillingStorage:
    payments: dict[UUID, dict[str, Any]] = field(default_factory=dict)
    refunds: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add_payment(
        self,
        *,
        payment_id: UUID,
        customer_id: UUID,
        amount: Decimal,
        currency: str = "CNY",
        status: str = "succeeded",
    ) -> dict[str, Any]:
        payment = {
            "payment_id": str(payment_id),
            "customer_id": str(customer_id),
            "amount": str(amount),
            "currency": currency,
            "status": status,
        }
        self.payments[payment_id] = payment
        return payment

    def preview_refund(
        self,
        *,
        payment_id: UUID,
        amount: Decimal,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payment = self.payments.get(payment_id)
        if payment is None:
            raise KeyError("payment not found")
        if amount <= Decimal("0.00") or amount > Decimal(payment["amount"]):
            raise ValueError("invalid refund amount")
        existing = self.refunds.get(idempotency_key)
        if existing is not None:
            return {
                "payment_id": str(payment_id),
                "amount": str(amount),
                "idempotency_key": idempotency_key,
                "status": existing["status"],
            }
        return {
            "payment_id": str(payment_id),
            "amount": str(amount),
            "idempotency_key": idempotency_key,
            "status": "previewed",
        }

    def execute_refund(
        self,
        *,
        payment_id: UUID,
        amount: Decimal,
        idempotency_key: str,
    ) -> dict[str, Any]:
        preview = self.preview_refund(
            payment_id=payment_id,
            amount=amount,
            idempotency_key=idempotency_key,
        )
        if preview["status"] == "succeeded":
            return {**self.refunds[idempotency_key], "created": False}
        refund = {
            "refund_id": str(uuid4()),
            "payment_id": str(payment_id),
            "amount": str(amount),
            "idempotency_key": idempotency_key,
            "status": "succeeded",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created": True,
        }
        self.refunds[idempotency_key] = refund
        return refund

    def get_refund(self, idempotency_key: str) -> dict[str, Any] | None:
        return self.refunds.get(idempotency_key)


@dataclass
class MockCrmStorage:
    customers: dict[UUID, dict[str, Any]] = field(default_factory=dict)

    def add_customer(
        self,
        *,
        customer_id: UUID,
        name: str,
        support_tier: str = "standard",
    ) -> dict[str, Any]:
        customer = {
            "customer_id": str(customer_id),
            "name": name,
            "support_tier": support_tier,
            "status": "active",
        }
        self.customers[customer_id] = customer
        return customer

    def get_customer(self, customer_id: UUID) -> dict[str, Any] | None:
        return self.customers.get(customer_id)


@dataclass
class MockMonitoringStorage:
    incidents: list[dict[str, Any]] = field(default_factory=list)

    def add_incident(self, service: str, severity: str, summary: str) -> dict[str, Any]:
        incident = {
            "incident_id": str(uuid4()),
            "service": service,
            "severity": severity,
            "summary": summary,
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.incidents.append(incident)
        return incident

    def list_incidents(self) -> list[dict[str, Any]]:
        return list(self.incidents)


@dataclass
class MockNotificationStorage:
    notifications: list[dict[str, Any]] = field(default_factory=list)

    def send(self, recipient: str, channel: str, message: str) -> dict[str, Any]:
        notification = {
            "notification_id": str(uuid4()),
            "recipient": recipient,
            "channel": channel,
            "message": message,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.notifications.append(notification)
        return notification

    def list_notifications(self) -> list[dict[str, Any]]:
        return list(self.notifications)
