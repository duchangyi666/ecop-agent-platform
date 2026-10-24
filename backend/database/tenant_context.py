from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_tenant_context(session: AsyncSession, tenant_id: UUID) -> None:
    """Bind the current transaction to a tenant for PostgreSQL RLS.

    `set_config(..., true)` is transaction-local, so a pooled connection cannot
    leak one tenant's scope into the next request. Calls outside a transaction
    start one implicitly; the caller is responsible for commit/rollback.
    """

    await session.execute(
        text("select set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


__all__ = ["set_tenant_context"]
