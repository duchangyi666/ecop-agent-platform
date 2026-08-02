from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_refund_approval_and_checkpoint_schema_is_migrated(database_url: str) -> None:
    engine = create_async_engine(database_url, pool_pre_ping=True)

    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda sync_connection: inspect(sync_connection).get_table_names())
        approval_columns = await connection.run_sync(
            lambda sync_connection: {
                item["name"] for item in inspect(sync_connection).get_columns("approval_requests")
            }
        )
        checkpoint_columns = await connection.run_sync(
            lambda sync_connection: {
                item["name"] for item in inspect(sync_connection).get_columns("workflow_checkpoints")
            }
        )

    await engine.dispose()

    assert "workflow_checkpoints" in tables
    assert "refund_id" in approval_columns
    assert {"tenant_id", "thread_id", "state_summary", "trace_id"}.issubset(checkpoint_columns)
