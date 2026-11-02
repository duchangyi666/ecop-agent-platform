from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.dependencies import RequestContext, get_session_factory_dependency, require_permission
from backend.auth.permissions import Permission
from backend.database.models.governance import MemoryRecord
from backend.database.unit_of_work import UnitOfWork

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
