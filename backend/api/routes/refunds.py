from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.refund_workflow import RefundWorkflowRequest
from backend.agent.runtime import run_refund_workflow
from backend.agent.state import create_agent_state
from backend.api.dependencies import (
    RequestContext,
    get_database_url,
    get_request_context,
    get_session_factory_dependency,
)
from backend.api.schemas import RefundCreateRequest, RefundResponse, WorkflowStatusResponse
from backend.database.unit_of_work import UnitOfWork

router = APIRouter(prefix="/api/v1", tags=["refunds"])


@router.post("/refunds", response_model=RefundResponse)
async def create_refund(
    payload: RefundCreateRequest,
    response: Response,
    context: RequestContext = Depends(get_request_context),
    database_url: str = Depends(get_database_url),
) -> RefundResponse:
    request = RefundWorkflowRequest(
        thread_id=payload.thread_id,
        state=create_agent_state(
            scope=context.scope,
            request_id=uuid4(),
            message=payload.message,
        ),
        payment_id=payload.payment_id,
        amount=payload.amount,
        refund_idempotency_key=payload.refund_idempotency_key,
    )
    result = await run_refund_workflow(request, database_url=database_url)
    if result.status == "awaiting_approval":
        response.status_code = status.HTTP_202_ACCEPTED
    elif result.status == "rejected":
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    return RefundResponse.from_result(request_id=context.request_id, result=result)


@router.get("/workflows/{thread_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    thread_id: str,
    context: RequestContext = Depends(get_request_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> WorkflowStatusResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        checkpoint = await uow.governance.get_workflow_checkpoint(
            scope=context.scope,
            thread_id=thread_id,
        )
        if checkpoint is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "workflow_not_found", "message": "workflow checkpoint not found"},
            )
        summary = checkpoint.state_summary or {}
        return WorkflowStatusResponse(
            request_id=context.request_id,
            thread_id=checkpoint.thread_id,
            status=checkpoint.status,
            next_action=summary.get("next_action"),
            refund_id=summary.get("refund_id"),
            approval_request_id=summary.get("approval_request_id"),
            trace_id=checkpoint.trace_id,
            has_refund_idempotency_key=bool(checkpoint.refund_idempotency_key),
        )


__all__ = ["router"]
