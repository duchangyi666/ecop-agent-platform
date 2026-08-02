from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.database.base import TenantScope
from backend.database.unit_of_work import UnitOfWork


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _optional_uuid(value: Any) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


class CheckpointStore(Protocol):
    async def save(self, thread_id: str, state: dict[str, Any]) -> None: ...

    async def load(self, thread_id: str) -> dict[str, Any] | None: ...


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}

    async def save(self, thread_id: str, state: dict[str, Any]) -> None:
        self._states[thread_id] = deepcopy(state)

    async def load(self, thread_id: str) -> dict[str, Any] | None:
        state = self._states.get(thread_id)
        return deepcopy(state) if state is not None else None


class DatabaseCheckpointStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        scope: TenantScope,
    ) -> None:
        self.session_factory = session_factory
        self.scope = scope

    async def save(self, thread_id: str, state: dict[str, Any]) -> None:
        state_summary = state.get("state", state)
        trace_id = _optional_uuid(state_summary.get("trace_id")) if isinstance(state_summary, dict) else None
        async with UnitOfWork(self.session_factory, scope=self.scope) as uow:
            await uow.governance.save_workflow_checkpoint(
                scope=self.scope,
                thread_id=thread_id,
                state_summary=_jsonable(state_summary),
                refund_idempotency_key=str(state.get("refund_idempotency_key", "")),
                status=str(state.get("status", "running")),
                trace_id=trace_id,
            )

    async def load(self, thread_id: str) -> dict[str, Any] | None:
        async with UnitOfWork(self.session_factory, scope=self.scope) as uow:
            checkpoint = await uow.governance.get_workflow_checkpoint(
                scope=self.scope,
                thread_id=thread_id,
            )
            if checkpoint is None:
                return None
            return {
                "state": deepcopy(checkpoint.state_summary),
                "refund_idempotency_key": checkpoint.refund_idempotency_key,
                "status": checkpoint.status,
            }


__all__ = ["CheckpointStore", "DatabaseCheckpointStore", "InMemoryCheckpointStore"]
