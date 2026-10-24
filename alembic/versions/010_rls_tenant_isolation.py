"""enable tenant row-level security on business tables

Revision ID: 010
Revises: 009
Create Date: 2026-10-24 10:30:00.000000

This is the first RLS rollout. It intentionally uses ENABLE (not FORCE) so the
local table owner can still run migrations/tests; production must connect as a
non-owner `app_rw` role for the policies to apply. A later migration can add
FORCE once every direct-session access path sets `app.tenant_id`.
"""

from __future__ import annotations

from alembic import op


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

# Login/dev identity lookups run before a tenant scope exists and are therefore
# handled by the identity service/role rather than row policies.
_EXCLUDED_TABLES = ("users", "roles", "permissions", "user_roles")


def upgrade() -> None:
    excluded = ", ".join(f"'{name}'" for name in _EXCLUDED_TABLES)
    op.execute(
        f"""
        DO $$
        DECLARE t record;
        BEGIN
          FOR t IN
            SELECT c.table_name
            FROM information_schema.columns c
            JOIN information_schema.tables tb
              ON tb.table_schema = c.table_schema
             AND tb.table_name = c.table_name
            WHERE c.table_schema = 'public'
              AND c.column_name = 'tenant_id'
              AND tb.table_type = 'BASE TABLE'
              AND c.table_name NOT IN ({excluded})
          LOOP
            EXECUTE format(
              'ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',
              t.table_name
            );
            IF NOT EXISTS (
              SELECT 1 FROM pg_policies
              WHERE schemaname = 'public'
                AND tablename = t.table_name
                AND policyname = 'tenant_isolation'
            ) THEN
              EXECUTE format(
                'CREATE POLICY tenant_isolation ON public.%I '
                'USING (tenant_id = current_setting(''app.tenant_id'', true)::uuid) '
                'WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true)::uuid)',
                t.table_name
              );
            END IF;
          END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    excluded = ", ".join(f"'{name}'" for name in _EXCLUDED_TABLES)
    op.execute(
        f"""
        DO $$
        DECLARE t record;
        BEGIN
          FOR t IN
            SELECT c.table_name
            FROM information_schema.columns c
            JOIN information_schema.tables tb
              ON tb.table_schema = c.table_schema
             AND tb.table_name = c.table_name
            WHERE c.table_schema = 'public'
              AND c.column_name = 'tenant_id'
              AND tb.table_type = 'BASE TABLE'
              AND c.table_name NOT IN ({excluded})
          LOOP
            EXECUTE format(
              'DROP POLICY IF EXISTS tenant_isolation ON public.%I',
              t.table_name
            );
            EXECUTE format(
              'ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY',
              t.table_name
            );
          END LOOP;
        END $$;
        """
    )
