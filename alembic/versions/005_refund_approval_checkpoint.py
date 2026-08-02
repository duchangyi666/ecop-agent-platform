"""add refund approval target and durable workflow checkpoints

Revision ID: 005
Revises: 004
Create Date: 2026-08-02 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("approval_requests", "ticket_id", existing_type=sa.UUID(), nullable=True)
    op.add_column("approval_requests", sa.Column("refund_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_approval_requests_refund_id"), "approval_requests", ["refund_id"], unique=False)
    op.create_foreign_key(
        "fk_approval_requests_tenant_refund",
        "approval_requests",
        "refunds",
        ["tenant_id", "refund_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_approval_requests_ticket_or_refund",
        "approval_requests",
        "ticket_id IS NOT NULL OR refund_id IS NOT NULL",
    )

    op.create_table(
        "workflow_checkpoints",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.String(length=160), nullable=False),
        sa.Column("state_summary", sa.JSON(), nullable=False),
        sa.Column("refund_idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("trace_id", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "trace_id"],
            ["runtime_traces.tenant_id", "runtime_traces.id"],
            name="fk_workflow_checkpoints_tenant_trace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_workflow_checkpoints_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_checkpoints")),
        sa.UniqueConstraint("tenant_id", "thread_id", name="uq_workflow_checkpoints_tenant_thread"),
    )
    op.create_index(op.f("ix_workflow_checkpoints_tenant_id"), "workflow_checkpoints", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_workflow_checkpoints_trace_id"), "workflow_checkpoints", ["trace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_workflow_checkpoints_trace_id"), table_name="workflow_checkpoints")
    op.drop_index(op.f("ix_workflow_checkpoints_tenant_id"), table_name="workflow_checkpoints")
    op.drop_table("workflow_checkpoints")

    op.drop_constraint("ck_approval_requests_ticket_or_refund", "approval_requests", type_="check")
    op.drop_constraint("fk_approval_requests_tenant_refund", "approval_requests", type_="foreignkey")
    op.drop_index(op.f("ix_approval_requests_refund_id"), table_name="approval_requests")
    op.drop_column("approval_requests", "refund_id")
    op.alter_column("approval_requests", "ticket_id", existing_type=sa.UUID(), nullable=False)
