"""support tables

Revision ID: 003
Revises: 002
Create Date: 2026-08-01 19:34:22.230449
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=True),
        sa.Column("metadata_summary", sa.JSON(), nullable=False),
        sa.Column("metadata_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_id"],
            ["users.tenant_id", "users.id"],
            name="fk_audit_logs_tenant_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_audit_logs_tenant_id_tenants"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_resource_id"), "audit_logs", ["resource_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_tenant_id"), "audit_logs", ["tenant_id"], unique=False)

    op.create_table(
        "tickets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("description_summary", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("priority", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "in_progress",
                "pending_customer",
                "pending_approval",
                "escalated",
                "resolved",
                "closed",
                "reopened",
                "cancelled",
                name="ticket_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("current_assignee_id", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "current_assignee_id"],
            ["users.tenant_id", "users.id"],
            name="fk_tickets_tenant_current_assignee",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_tickets_tenant_customer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_tickets_tenant_id_tenants"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tickets_tenant_id_id"),
    )
    op.create_index(op.f("ix_tickets_current_assignee_id"), "tickets", ["current_assignee_id"], unique=False)
    op.create_index(op.f("ix_tickets_customer_id"), "tickets", ["customer_id"], unique=False)
    op.create_index(op.f("ix_tickets_tenant_id"), "tickets", ["tenant_id"], unique=False)

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("requested_by_user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("payload_summary", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("risk_level", sa.String(length=50), nullable=False),
        sa.Column("approval_role", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "approved",
                "rejected",
                "modified",
                "expired",
                "more_information_required",
                name="approval_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checkpoint_reference", sa.String(length=255), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requested_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_approval_requests_tenant_requested_by_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "ticket_id"],
            ["tickets.tenant_id", "tickets.id"],
            name="fk_approval_requests_tenant_ticket",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_approval_requests_tenant_id_tenants"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_requests")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_approval_requests_tenant_id_id"),
    )
    op.create_index(op.f("ix_approval_requests_requested_by_user_id"), "approval_requests", ["requested_by_user_id"], unique=False)
    op.create_index(op.f("ix_approval_requests_tenant_id"), "approval_requests", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_approval_requests_ticket_id"), "approval_requests", ["ticket_id"], unique=False)

    op.create_table(
        "ticket_assignments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("assigned_user_id", sa.UUID(), nullable=False),
        sa.Column("assigned_by_user_id", sa.UUID(), nullable=True),
        sa.Column("reason_summary", sa.String(length=255), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assigned_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_ticket_assignments_tenant_assigned_by_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assigned_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_ticket_assignments_tenant_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "ticket_id"],
            ["tickets.tenant_id", "tickets.id"],
            name="fk_ticket_assignments_tenant_ticket",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_ticket_assignments_tenant_id_tenants"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_assignments")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_ticket_assignments_tenant_id_id"),
    )
    op.create_index(op.f("ix_ticket_assignments_assigned_by_user_id"), "ticket_assignments", ["assigned_by_user_id"], unique=False)
    op.create_index(op.f("ix_ticket_assignments_assigned_user_id"), "ticket_assignments", ["assigned_user_id"], unique=False)
    op.create_index(op.f("ix_ticket_assignments_tenant_id"), "ticket_assignments", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_ticket_assignments_ticket_id"), "ticket_assignments", ["ticket_id"], unique=False)

    op.create_table(
        "ticket_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column(
            "from_status",
            sa.Enum(
                "open",
                "in_progress",
                "pending_customer",
                "pending_approval",
                "escalated",
                "resolved",
                "closed",
                "reopened",
                "cancelled",
                name="ticket_status",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            sa.Enum(
                "open",
                "in_progress",
                "pending_customer",
                "pending_approval",
                "escalated",
                "resolved",
                "closed",
                "reopened",
                "cancelled",
                name="ticket_status",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("payload_summary", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_id"],
            ["users.tenant_id", "users.id"],
            name="fk_ticket_events_tenant_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "ticket_id"],
            ["tickets.tenant_id", "tickets.id"],
            name="fk_ticket_events_tenant_ticket",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_ticket_events_tenant_id_tenants"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_events")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_ticket_events_tenant_id_id"),
    )
    op.create_index(op.f("ix_ticket_events_actor_id"), "ticket_events", ["actor_id"], unique=False)
    op.create_index(op.f("ix_ticket_events_tenant_id"), "ticket_events", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_ticket_events_ticket_id"), "ticket_events", ["ticket_id"], unique=False)

    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(length=50), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "author_id"],
            ["users.tenant_id", "users.id"],
            name="fk_ticket_messages_tenant_author",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "ticket_id"],
            ["tickets.tenant_id", "tickets.id"],
            name="fk_ticket_messages_tenant_ticket",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_ticket_messages_tenant_id_tenants"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_messages")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_ticket_messages_tenant_id_id"),
    )
    op.create_index(op.f("ix_ticket_messages_author_id"), "ticket_messages", ["author_id"], unique=False)
    op.create_index(op.f("ix_ticket_messages_tenant_id"), "ticket_messages", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_ticket_messages_ticket_id"), "ticket_messages", ["ticket_id"], unique=False)

    op.create_table(
        "approval_actions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("approval_request_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changes_summary", sa.JSON(), nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_id"],
            ["users.tenant_id", "users.id"],
            name="fk_approval_actions_tenant_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "approval_request_id"],
            ["approval_requests.tenant_id", "approval_requests.id"],
            name="fk_approval_actions_tenant_request",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_approval_actions_tenant_id_tenants"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_actions")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_approval_actions_tenant_id_id"),
    )
    op.create_index(op.f("ix_approval_actions_actor_id"), "approval_actions", ["actor_id"], unique=False)
    op.create_index(op.f("ix_approval_actions_approval_request_id"), "approval_actions", ["approval_request_id"], unique=False)
    op.create_index(op.f("ix_approval_actions_tenant_id"), "approval_actions", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_approval_actions_tenant_id"), table_name="approval_actions")
    op.drop_index(op.f("ix_approval_actions_approval_request_id"), table_name="approval_actions")
    op.drop_index(op.f("ix_approval_actions_actor_id"), table_name="approval_actions")
    op.drop_table("approval_actions")
    op.drop_index(op.f("ix_ticket_messages_ticket_id"), table_name="ticket_messages")
    op.drop_index(op.f("ix_ticket_messages_tenant_id"), table_name="ticket_messages")
    op.drop_index(op.f("ix_ticket_messages_author_id"), table_name="ticket_messages")
    op.drop_table("ticket_messages")
    op.drop_index(op.f("ix_ticket_events_ticket_id"), table_name="ticket_events")
    op.drop_index(op.f("ix_ticket_events_tenant_id"), table_name="ticket_events")
    op.drop_index(op.f("ix_ticket_events_actor_id"), table_name="ticket_events")
    op.drop_table("ticket_events")
    op.drop_index(op.f("ix_ticket_assignments_ticket_id"), table_name="ticket_assignments")
    op.drop_index(op.f("ix_ticket_assignments_tenant_id"), table_name="ticket_assignments")
    op.drop_index(op.f("ix_ticket_assignments_assigned_user_id"), table_name="ticket_assignments")
    op.drop_index(op.f("ix_ticket_assignments_assigned_by_user_id"), table_name="ticket_assignments")
    op.drop_table("ticket_assignments")
    op.drop_index(op.f("ix_approval_requests_ticket_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_tenant_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_requested_by_user_id"), table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index(op.f("ix_tickets_tenant_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_customer_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_current_assignee_id"), table_name="tickets")
    op.drop_table("tickets")
    op.drop_index(op.f("ix_audit_logs_tenant_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_resource_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
