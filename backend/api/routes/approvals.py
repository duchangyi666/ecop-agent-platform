from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.approval_workflow import resume_refund_after_approval
from backend.api.dependencies import (
    RequestContext,
    get_database_url,
    get_session_factory_dependency,
    require_permission,
)
from backend.api.schemas import (
    ApprovalActionItem,
    ApprovalActionRequest,
    ApprovalDetailResponse,
    ApprovalItem,
    ApprovalListResponse,
    RefundResponse,
)
from backend.auth.permissions import Permission
from backend.database.unit_of_work import UnitOfWork
from backend.domain.approval import ApprovalStatus

router = APIRouter(prefix="/api/v1", tags=["approvals"])


def _approval_item(approval, *, as_of: datetime) -> ApprovalItem:
    actions = getattr(approval, "actions", None) or []
    effective_status = approval.status
    if effective_status == ApprovalStatus.PENDING and approval.expires_at <= as_of:
        effective_status = ApprovalStatus.EXPIRED
    return ApprovalItem(
        approval_request_id=approval.id,
        ticket_id=approval.ticket_id,
        refund_id=approval.refund_id,
        action=approval.action,
        amount=approval.amount,
        risk_level=approval.risk_level,
        approval_role=approval.approval_role,
        status=effective_status.value if hasattr(effective_status, "value") else str(effective_status),
        expires_at=approval.expires_at,
        checkpoint_reference=approval.checkpoint_reference,
        action_count=len(actions),
    )


def _action_item(action) -> ApprovalActionItem:
    return ApprovalActionItem(
        action_id=action.id,
        actor_id=action.actor_id,
        action=action.action,
        reason=action.reason,
        changes_summary=action.changes_summary,
        acted_at=action.acted_at,
    )


@router.get("/approvals", response_model=ApprovalListResponse)
async def list_approvals(
    context: RequestContext = Depends(require_permission(Permission.APPROVAL_READ)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
    status_filter: str | None = Query(default=None, alias="status", max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
) -> ApprovalListResponse:
    as_of = datetime.now(timezone.utc)
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        approvals = await uow.support.list_approval_requests(
            scope=context.scope,
            limit=limit,
            status=status_filter,
            as_of=as_of,
        )
    return ApprovalListResponse(
        request_id=context.request_id,
        approvals=[_approval_item(item, as_of=as_of) for item in approvals],
    )


@router.get("/approvals/{approval_request_id}", response_model=ApprovalDetailResponse)
async def get_approval(
    approval_request_id: UUID,
    context: RequestContext = Depends(require_permission(Permission.APPROVAL_READ)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> ApprovalDetailResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        approval = await uow.support.get_approval_request_for_tenant(
            scope=context.scope,
            approval_request_id=approval_request_id,
        )
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "approval_not_found", "message": "approval request not found"},
        )
    return ApprovalDetailResponse(
        request_id=context.request_id,
        approval=_approval_item(approval, as_of=datetime.now(timezone.utc)),
        actions=[_action_item(action) for action in approval.actions],
    )


@router.post("/approvals/{approval_request_id}", response_model=RefundResponse)
async def act_on_approval(
    approval_request_id: UUID,
    payload: ApprovalActionRequest,
    context: RequestContext = Depends(require_permission(Permission.REFUND_APPROVE)),
    database_url: str = Depends(get_database_url),
) -> RefundResponse:
    result = await resume_refund_after_approval(
        database_url=database_url,
        scope=context.scope,
        thread_id=payload.thread_id,
        approval_request_id=approval_request_id,
        approved=payload.approved,
        actor_id=context.scope.actor_id,
        reason=payload.reason,
    )
    return RefundResponse.from_result(request_id=context.request_id, result=result)


__all__ = ["router"]
