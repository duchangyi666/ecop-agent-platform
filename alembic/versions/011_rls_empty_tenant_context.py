"""Treat an empty transaction-local tenant context as absent in RLS policies.

Revision ID: 011
Revises: 010
"""

from __future__ import annotations

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def _update_policies(*, empty_is_null: bool) -> None:
    # PostgreSQL can retain an empty custom setting after SET LOCAL ends.
    # NULL makes both USING and WITH CHECK deny access without a UUID cast error.
    setting = "current_setting(''app.tenant_id'', true)"
    if empty_is_null:
        setting = f"nullif({setting}, '''')"
    predicate = f"tenant_id = {setting}::uuid"
    op.execute(
        f"""
        DO $$
        DECLARE policy record;
        BEGIN
          FOR policy IN
            SELECT schemaname, tablename FROM pg_policies
            WHERE schemaname = 'public' AND policyname = 'tenant_isolation'
          LOOP
            EXECUTE format(
              'ALTER POLICY tenant_isolation ON %I.%I USING ({predicate}) '
              'WITH CHECK ({predicate})', policy.schemaname, policy.tablename
            );
          END LOOP;
        END $$;
        """
    )


def upgrade() -> None:
    _update_policies(empty_is_null=True)


def downgrade() -> None:
    _update_policies(empty_is_null=False)
