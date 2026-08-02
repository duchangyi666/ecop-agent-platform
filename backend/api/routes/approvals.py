from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from backend.agent.approval_workflow import resume_refund_after_approval
from backend.api.dependencies import RequestContext, get_database_url, require_permission
from backend.api.schemas import ApprovalActionRequest, RefundResponse

router = APIRouter(prefix="/api/v1", tags=["approvals"])


@router.post("/approvals/{approval_request_id}", response_model=RefundResponse)
async def act_on_approval(
    approval_request_id: UUID,
    payload: ApprovalActionRequest,
    context: RequestContext = Depends(require_permission("refund.approve")),
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
