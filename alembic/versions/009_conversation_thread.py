"""add conversation thread id for multi-turn persistence

Revision ID: 009
Revises: 008
Create Date: 2026-08-03 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("thread_id", sa.String(length=160), nullable=True),
    )
    op.create_index(
        op.f("ix_conversations_thread_id"), "conversations", ["thread_id"], unique=False
    )
    op.create_unique_constraint(
        "uq_conversations_tenant_id_thread_id", "conversations", ["tenant_id", "thread_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_conversations_tenant_id_thread_id", "conversations", type_="unique")
    op.drop_index(op.f("ix_conversations_thread_id"), table_name="conversations")
    op.drop_column("conversations", "thread_id")
