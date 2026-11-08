"""Order consultation messages by turn, not timestamp ties.

Revision ID: 013
Revises: 012
Create Date: 2026-11-08 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_messages",
        sa.Column("turn_sequence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        WITH numbered AS (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY conversation_id
                ORDER BY created_at ASC, id ASC
            ) AS seq
            FROM conversation_messages
        )
        UPDATE conversation_messages AS message
        SET turn_sequence = numbered.seq
        FROM numbered
        WHERE message.id = numbered.id
        """
    )
    op.alter_column("conversation_messages", "turn_sequence", server_default=None)
    op.create_unique_constraint(
        "uq_conversation_messages_conversation_turn_role",
        "conversation_messages",
        ["conversation_id", "turn_sequence", "role"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_conversation_messages_conversation_turn_role",
        "conversation_messages",
        type_="unique",
    )
    op.drop_column("conversation_messages", "turn_sequence")
