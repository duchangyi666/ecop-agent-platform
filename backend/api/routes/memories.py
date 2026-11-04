from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.dependencies import RequestContext, get_session_factory_dependency, require_permission
from backend.auth.permissions import Permission
from backend.database.models.governance import MemoryRecord
from backend.database.unit_of_work import UnitOfWork
from backend.database.models.identity import User
from backend.memory.service import MemoryService
from backend.memory.candidates import MemoryCandidate, DeterministicMemoryExtractor
from backend.memory.policy import MemoryWritePolicy
from backend.agent.guards import InputSecurityGuard

router = APIRouter(prefix="/api/v1/memories", tags=["memories"])


class MemoryItem(BaseModel):
    memory_id: UUID
    memory_type: str
    content: str
    created_at: datetime
    last_active_at: datetime
    expires_at: datetime


class MemoryListResponse(BaseModel):
    request_id: str
    memories: list[MemoryItem]


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    context: RequestContext = Depends(require_permission(Permission.CUSTOMER_CONSULT)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
    limit: int = Query(default=50, ge=1, le=100),
) -> MemoryListResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        rows = list(await uow.session.scalars(select(MemoryRecord).where(
            MemoryRecord.tenant_id == context.scope.tenant_id,
            MemoryRecord.user_id == context.scope.actor_id,
            MemoryRecord.deleted_at.is_(None),
            MemoryRecord.ttl_expires_at > datetime.now(timezone.utc),
        ).order_by(MemoryRecord.created_at.desc(), MemoryRecord.id).limit(limit)))
    return MemoryListResponse(request_id=context.request_id, memories=[
        MemoryItem(memory_id=row.id, memory_type=row.memory_type,
                   content=str(row.payload_summary.get("content", "")),
                   created_at=row.created_at, last_active_at=row.updated_at,
                   expires_at=row.ttl_expires_at)
        for row in rows
    ])


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: UUID,
    context: RequestContext = Depends(require_permission(Permission.CUSTOMER_CONSULT)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> Response:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        deleted = await uow.session.scalar(update(MemoryRecord).where(
            MemoryRecord.id == memory_id,
            MemoryRecord.tenant_id == context.scope.tenant_id,
            MemoryRecord.user_id == context.scope.actor_id,
            MemoryRecord.deleted_at.is_(None),
        ).values(deleted_at=datetime.now(timezone.utc)).returning(MemoryRecord.id))
        if deleted is None:
            raise HTTPException(status_code=404, detail={"code": "memory_not_found", "message": "memory not found"})
    return Response(status_code=204)


class MemoryCorrectionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    value: str = Field(min_length=1, max_length=200)


@router.patch("/{memory_id}", response_model=MemoryItem)
async def correct_memory(
    memory_id: UUID,
    payload: MemoryCorrectionRequest,
    context: RequestContext = Depends(require_permission(Permission.CUSTOMER_CONSULT)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> MemoryItem:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        # Use the same owner-first lock ordering as automatic memory capture.
        await uow.session.scalar(select(User.id).where(
            User.tenant_id == context.scope.tenant_id, User.id == context.scope.actor_id,
        ).with_for_update())
        now = datetime.now(timezone.utc)
        record = await uow.session.scalar(select(MemoryRecord).where(
            MemoryRecord.id == memory_id, MemoryRecord.tenant_id == context.scope.tenant_id,
            MemoryRecord.user_id == context.scope.actor_id,
            MemoryRecord.deleted_at.is_(None), MemoryRecord.ttl_expires_at > now,
        ).with_for_update())
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "memory_not_found", "message": "memory not found"})
        value = payload.value
        if record.memory_type == "language_preference" and value in {"zh", "en"}:
            content, ttl = f"preferred_language={value}", 365
        elif record.memory_type == "timezone_preference" and DeterministicMemoryExtractor._valid_timezone(value):
            content, ttl = f"timezone={value}", 365
        elif record.memory_type == "user_preference":
            content, ttl = f"preference={value}", 90
        else:
            raise HTTPException(status_code=422, detail={"code": "invalid_memory_value", "message": "invalid preference value"})
        candidate = MemoryCandidate(record.memory_type, content, 0.9, ttl, source="user_correction")
        if not MemoryWritePolicy().allow(candidate) or InputSecurityGuard().evaluate(value).status != "allow":
            raise HTTPException(status_code=422, detail={"code": "invalid_memory_value", "message": "preference did not pass validation"})
        record.deleted_at = now
        await uow.session.flush()
        records = await MemoryService().store_candidates_in_uow(
            uow, scope=context.scope, user_id=context.scope.actor_id,
            customer_id=record.customer_id, candidates=[candidate],
        )
        updated = records[0]
        return MemoryItem(memory_id=updated.id, memory_type=updated.memory_type,
                          content=updated.payload_summary["content"], created_at=updated.created_at,
                          last_active_at=updated.updated_at, expires_at=updated.ttl_expires_at)
