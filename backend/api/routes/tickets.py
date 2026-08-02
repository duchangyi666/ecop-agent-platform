from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.state import create_agent_state
from backend.agent.ticket_workflow import (
    TicketWorkflowRequest,
    TicketWorkflowService,
)
from backend.api.dependencies import (
    RequestContext,
    get_session_factory_dependency,
    require_permission,
)
from backend.api.schemas import TicketCreateRequest, TicketResponse

router = APIRouter(prefix="/api/v1", tags=["tickets"])


@router.post("/tickets", response_model=TicketResponse)
async def create_ticket(
    payload: TicketCreateRequest,
    response: Response,
    context: RequestContext = Depends(require_permission("ticket.create")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> TicketResponse:
    result = await TicketWorkflowService(session_factory).run(
        TicketWorkflowRequest(
            thread_id=payload.thread_id,
            state=create_agent_state(
                scope=context.scope,
                request_id=uuid4(),
                message="请创建工单",
            ),
            customer_id=payload.customer_id,
            subject=payload.subject,
            priority=payload.priority,
            description_summary=payload.description_summary,
            message=payload.message,
        )
    )

    if result.status == "blocked":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "security_blocked",
                "message": result.final_response,
            },
        )
    if result.status == "out_of_scope":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "out_of_scope",
                "message": result.final_response,
            },
        )
    if result.status == "human_handoff":
        response.status_code = status.HTTP_202_ACCEPTED
    elif result.status == "ticket_created":
        response.status_code = status.HTTP_201_CREATED

    return TicketResponse.from_result(request_id=context.request_id, result=result)


__all__ = ["router"]
