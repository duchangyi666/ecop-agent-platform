from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, cast, func, select

from backend.database.base import TenantScope
from backend.database.models.governance import (
    AgentDefinition,
    RuntimeSpan,
    RuntimeTrace,
)
from backend.database.repositories.base import TenantScopedRepository


class RuntimeRepository(TenantScopedRepository):
    async def list_traces(
        self,
        *,
        scope: TenantScope,
        limit: int = 50,
    ) -> list[RuntimeTrace]:
        statement = (
            self._tenant_visible(
                select(RuntimeTrace),
                RuntimeTrace,
                scope=scope,
            )
            .order_by(RuntimeTrace.started_at.desc())
            .limit(limit)
        )
        return list(await self.session.scalars(statement))

    async def get_trace(
        self,
        *,
        scope: TenantScope,
        trace_id: UUID,
    ) -> RuntimeTrace | None:
        statement = self._tenant_visible(
            select(RuntimeTrace),
            RuntimeTrace,
            scope=scope,
        ).where(RuntimeTrace.id == trace_id)
        return await self.session.scalar(statement)

    async def list_spans(
        self,
        *,
        scope: TenantScope,
        trace_id: UUID,
    ) -> list[RuntimeSpan]:
        statement = (
            self._tenant_visible(
                select(RuntimeSpan),
                RuntimeSpan,
                scope=scope,
            )
            .where(RuntimeSpan.trace_id == trace_id)
            .order_by(RuntimeSpan.started_at)
        )
        return list(await self.session.scalars(statement))

    async def list_agents(
        self,
        *,
        scope: TenantScope,
    ) -> list[AgentDefinition]:
        statement = (
            self._tenant_visible(
                select(AgentDefinition),
                AgentDefinition,
                scope=scope,
            )
            .order_by(AgentDefinition.agent_code)
        )
        return list(await self.session.scalars(statement))

    async def summary(
        self,
        *,
        scope: TenantScope,
    ) -> dict[str, Any]:
        statement = select(
            func.count(RuntimeTrace.id),
            func.coalesce(func.sum(RuntimeTrace.total_input_tokens), 0),
            func.coalesce(func.sum(RuntimeTrace.total_output_tokens), 0),
            func.coalesce(func.sum(RuntimeTrace.total_cost), Decimal("0.00")),
            func.coalesce(
                func.sum(
                    cast(RuntimeTrace.status.in_(("failed", "blocked")), Integer)
                ),
                0,
            ),
        ).where(
            RuntimeTrace.tenant_id == scope.tenant_id,
            RuntimeTrace.deleted_at.is_(None),
        )
        row = await self.session.execute(statement)
        trace_count, input_tokens, output_tokens, total_cost, failed_count = row.one()
        return {
            "trace_count": int(trace_count or 0),
            "total_input_tokens": int(input_tokens or 0),
            "total_output_tokens": int(output_tokens or 0),
            "total_cost": str(total_cost or Decimal("0.00")),
            "failed_count": int(failed_count or 0),
        }


__all__ = ["RuntimeRepository"]
