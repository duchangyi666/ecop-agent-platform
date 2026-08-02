from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, ForeignKeyConstraint, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base, TenantAuditMixin, money_type, utc_now
from backend.database.models.billing import Refund
from backend.domain.approval import ApprovalStatus
from backend.domain.ticket import TicketStatus


def _enum_values(enum_type: type[Enum]) -> list[str]:
    return [item.value for item in enum_type]


class Ticket(Base, TenantAuditMixin):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_tickets_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_tickets_tenant_customer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "current_assignee_id"],
            ["users.tenant_id", "users.id"],
            name="fk_tickets_tenant_current_assignee",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        SAEnum(
            TicketStatus,
            name="ticket_status",
            native_enum=False,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    current_assignee_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["TicketMessage"]] = relationship(back_populates="ticket")
    events: Mapped[list["TicketEvent"]] = relationship(back_populates="ticket")
    assignments: Mapped[list["TicketAssignment"]] = relationship(back_populates="ticket")
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(back_populates="ticket")


class TicketMessage(Base, TenantAuditMixin):
    __tablename__ = "ticket_messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ticket_messages_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "ticket_id"],
            ["tickets.tenant_id", "tickets.id"],
            name="fk_ticket_messages_tenant_ticket",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "author_id"],
            ["users.tenant_id", "users.id"],
            name="fk_ticket_messages_tenant_author",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    author_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(50), nullable=False)

    ticket: Mapped["Ticket"] = relationship(back_populates="messages")


class TicketEvent(Base, TenantAuditMixin):
    __tablename__ = "ticket_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ticket_events_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "ticket_id"],
            ["tickets.tenant_id", "tickets.id"],
            name="fk_ticket_events_tenant_ticket",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "actor_id"],
            ["users.tenant_id", "users.id"],
            name="fk_ticket_events_tenant_actor",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    actor_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    from_status: Mapped[TicketStatus | None] = mapped_column(
        SAEnum(
            TicketStatus,
            name="ticket_status",
            native_enum=False,
            values_callable=_enum_values,
        ),
        nullable=True,
    )
    to_status: Mapped[TicketStatus | None] = mapped_column(
        SAEnum(
            TicketStatus,
            name="ticket_status",
            native_enum=False,
            values_callable=_enum_values,
        ),
        nullable=True,
    )
    payload_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    ticket: Mapped["Ticket"] = relationship(back_populates="events")


class TicketAssignment(Base, TenantAuditMixin):
    __tablename__ = "ticket_assignments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ticket_assignments_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "ticket_id"],
            ["tickets.tenant_id", "tickets.id"],
            name="fk_ticket_assignments_tenant_ticket",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "assigned_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_ticket_assignments_tenant_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "assigned_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_ticket_assignments_tenant_assigned_by_user",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    assigned_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    assigned_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    reason_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ticket: Mapped["Ticket"] = relationship(back_populates="assignments")


class ApprovalRequest(Base, TenantAuditMixin):
    __tablename__ = "approval_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_approval_requests_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "ticket_id"],
            ["tickets.tenant_id", "tickets.id"],
            name="fk_approval_requests_tenant_ticket",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "refund_id"],
            ["refunds.tenant_id", "refunds.id"],
            name="fk_approval_requests_tenant_refund",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "requested_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_approval_requests_tenant_requested_by_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "ticket_id IS NOT NULL OR refund_id IS NOT NULL",
            name="ck_approval_requests_ticket_or_refund",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    refund_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    requested_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(money_type(), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False)
    approval_role: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        SAEnum(
            ApprovalStatus,
            name="approval_status",
            native_enum=False,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checkpoint_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    ticket: Mapped["Ticket"] = relationship(back_populates="approval_requests")
    refund: Mapped[Refund | None] = relationship(overlaps="approval_requests,ticket")
    actions: Mapped[list["ApprovalAction"]] = relationship(
        back_populates="approval_request",
        order_by="ApprovalAction.acted_at",
        cascade="save-update, merge",
    )


class ApprovalAction(Base, TenantAuditMixin):
    __tablename__ = "approval_actions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_approval_actions_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "approval_request_id"],
            ["approval_requests.tenant_id", "approval_requests.id"],
            name="fk_approval_actions_tenant_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "actor_id"],
            ["users.tenant_id", "users.id"],
            name="fk_approval_actions_tenant_actor",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    approval_request_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    actor_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    changes_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    approval_request: Mapped["ApprovalRequest"] = relationship(back_populates="actions")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "actor_id"],
            ["users.tenant_id", "users.id"],
            name="fk_audit_logs_tenant_actor",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    actor_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    metadata_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    metadata_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


__all__ = [
    "ApprovalAction",
    "ApprovalRequest",
    "AuditLog",
    "Ticket",
    "TicketAssignment",
    "TicketEvent",
    "TicketMessage",
]
