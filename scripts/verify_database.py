from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# 允许从项目根目录直接执行 `python scripts/verify_database.py`。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.database.base import Base
import backend.database.models  # noqa: F401


REQUIRED_UNIQUE_CONSTRAINTS = {
    ("payments", "uq_payments_tenant_id_external_payment_id"),
    ("refunds", "uq_refunds_tenant_id_idempotency_key"),
    ("approval_requests", "uq_approval_requests_tenant_id_id"),
    ("approval_actions", "uq_approval_actions_tenant_id_id"),
}


@dataclass(frozen=True, slots=True)
class SchemaVerificationReport:
    tables_found: list[str]
    tenant_scoped_tables: dict[str, bool]
    missing_constraints: list[str]
    status: str


def _expected_tables() -> set[str]:
    return set(Base.metadata.tables)


def _expected_tenant_tables() -> set[str]:
    return {
        table.name
        for table in Base.metadata.sorted_tables
        if "tenant_id" in table.c
    }


def _money_columns() -> dict[str, str]:
    return {
        "invoices.amount": "NUMERIC(18, 2)",
        "payments.amount": "NUMERIC(18, 2)",
        "refunds.amount": "NUMERIC(18, 2)",
        "approval_requests.amount": "NUMERIC(18, 2)",
        "runtime_traces.total_cost": "NUMERIC(18, 2)",
        "evaluation_results.score": "NUMERIC(18, 2)",
    }


async def _inspect_schema(engine: AsyncEngine) -> tuple[list[str], dict[str, list[dict[str, Any]]], dict[str, list[str]]]:
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda sync_connection: inspect(sync_connection).get_table_names())
        columns = await connection.run_sync(
            lambda sync_connection: {
                table: inspect(sync_connection).get_columns(table)
                for table in tables
            }
        )
        unique_constraints = await connection.run_sync(
            lambda sync_connection: {
                table: [item.get("name") for item in inspect(sync_connection).get_unique_constraints(table)]
                for table in tables
            }
        )
    return tables, columns, unique_constraints


async def verify_schema(database_url: str) -> SchemaVerificationReport:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        tables, columns, unique_constraints = await _inspect_schema(engine)
    finally:
        await engine.dispose()

    expected_tables = _expected_tables()
    missing_constraints = [f"table:{table}" for table in sorted(expected_tables - set(tables))]
    tenant_tables = _expected_tenant_tables()
    tenant_scoped_tables = {
        table: table in tables and "tenant_id" in {column["name"] for column in columns.get(table, [])}
        for table in sorted(tenant_tables)
    }
    missing_constraints.extend(
        f"tenant_id:{table}"
        for table, present in tenant_scoped_tables.items()
        if not present
    )

    for qualified_name, expected_type in _money_columns().items():
        table, column = qualified_name.split(".", maxsplit=1)
        actual = next((item for item in columns.get(table, []) if item["name"] == column), None)
        actual_type = str(actual["type"]).upper() if actual else "MISSING"
        if actual is None or "NUMERIC(18, 2)" not in actual_type:
            missing_constraints.append(f"money:{qualified_name} expected {expected_type}, found {actual_type}")

    for table, constraint in sorted(REQUIRED_UNIQUE_CONSTRAINTS):
        if constraint not in unique_constraints.get(table, []):
            missing_constraints.append(f"unique:{table}.{constraint}")

    return SchemaVerificationReport(
        tables_found=sorted(tables),
        tenant_scoped_tables=tenant_scoped_tables,
        missing_constraints=missing_constraints,
        status="passed" if not missing_constraints else "failed",
    )


async def verify_migrations(database_url: str) -> None:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await engine.dispose()
    if revision != "007":
        raise RuntimeError(f"expected Alembic revision 007, found {revision!r}")


async def _main() -> None:
    database_url = os.getenv("DATABASE_URL", get_settings().database_url)
    report = await verify_schema(database_url)
    await verify_migrations(database_url)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    if report.status != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(_main())
