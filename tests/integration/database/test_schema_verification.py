from __future__ import annotations

import pytest

from scripts.verify_database import verify_migrations, verify_schema


@pytest.mark.asyncio
async def test_schema_verification_reports_required_tables(database_url: str) -> None:
    report = await verify_schema(database_url)

    assert report.status == "passed"
    assert "tenants" in report.tables_found
    assert "refunds" in report.tables_found
    assert report.tenant_scoped_tables["payments"] is True
    assert report.missing_constraints == []


@pytest.mark.asyncio
async def test_migration_head_is_current(database_url: str) -> None:
    await verify_migrations(database_url)
