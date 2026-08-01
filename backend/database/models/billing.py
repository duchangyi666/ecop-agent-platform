from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base, TenantAuditMixin, money_type
from backend.domain.billing import PaymentStatus, RefundStatus


def _enum_values(enum_type: type[Enum]) -> list[str]:
    return [item.value for item in enum_type]


class Customer(Base, TenantAuditMixin):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_customer_id", name="uq_customers_tenant_id_external_customer_id"),
        UniqueConstraint("tenant_id", "id", name="uq_customers_tenant_id_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    external_customer_id: Mapped[str] = mapped_column(String(120), nullable=False)
    support_tier: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    contacts: Mapped[list["CustomerContact"]] = relationship(back_populates="customer")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="customer")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="customer", overlaps="subscription,invoices")
    payments: Mapped[list["Payment"]] = relationship(back_populates="customer", overlaps="invoice,payments")


class CustomerContact(Base, TenantAuditMixin):
    __tablename__ = "customer_contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_customer_contacts_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_customer_contacts_tenant_customer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_customer_contacts_tenant_user",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    masked_value: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(20), nullable=False)

    customer: Mapped["Customer"] = relationship(back_populates="contacts")


class Subscription(Base, TenantAuditMixin):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_subscriptions_tenant_id_id"),
        UniqueConstraint("tenant_id", "external_subscription_id", name="uq_subscriptions_tenant_id_external_subscription_id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_subscriptions_tenant_customer",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    external_subscription_id: Mapped[str] = mapped_column(String(120), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String(50), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="subscriptions")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="subscription", overlaps="customer,invoices")


class Invoice(Base, TenantAuditMixin):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_invoices_tenant_id_id"),
        UniqueConstraint("tenant_id", "external_invoice_id", name="uq_invoices_tenant_id_external_invoice_id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_invoices_tenant_customer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id"],
            ["subscriptions.tenant_id", "subscriptions.id"],
            name="fk_invoices_tenant_subscription",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    subscription_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    external_invoice_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    customer: Mapped["Customer"] = relationship(back_populates="invoices", overlaps="subscription,invoices")
    subscription: Mapped["Subscription | None"] = relationship(back_populates="invoices", overlaps="customer,invoices")
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice", overlaps="customer,payments")


class Payment(Base, TenantAuditMixin):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_payments_tenant_id_id"),
        UniqueConstraint("tenant_id", "external_payment_id", name="uq_payments_tenant_id_external_payment_id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_payments_tenant_customer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_payments_tenant_invoice",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    external_payment_id: Mapped[str] = mapped_column(String(120), nullable=False)
    amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(
            PaymentStatus,
            name="payment_status",
            native_enum=False,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    customer: Mapped["Customer"] = relationship(back_populates="payments", overlaps="invoice,payments")
    invoice: Mapped["Invoice"] = relationship(back_populates="payments", overlaps="customer,payments")
    refunds: Mapped[list["Refund"]] = relationship(back_populates="payment")


class Refund(Base, TenantAuditMixin):
    __tablename__ = "refunds"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_refunds_tenant_id_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_refunds_tenant_id_idempotency_key"),
        ForeignKeyConstraint(
            ["tenant_id", "payment_id"],
            ["payments.tenant_id", "payments.id"],
            name="fk_refunds_tenant_payment",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "requested_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_refunds_tenant_requested_by_user",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    payment_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RefundStatus] = mapped_column(
        SAEnum(
            RefundStatus,
            name="refund_status",
            native_enum=False,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    has_unknown_execution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    payment: Mapped["Payment"] = relationship(back_populates="refunds")


__all__ = [
    "Customer",
    "CustomerContact",
    "Subscription",
    "Invoice",
    "Payment",
    "Refund",
]
