from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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
from backend.api.schemas import (
    TicketCreateRequest,
    TicketDetailResponse,
    TicketEventItem,
    TicketListItem,
    TicketListResponse,
    TicketMessageItem,
    TicketPatchRequest,
    TicketResponse,
)
from backend.auth.permissions import Permission
from backend.database.unit_of_work import UnitOfWork
from backend.domain.ticket import TicketStatus

router = APIRouter(prefix="/api/v1", tags=["tickets"])


def _ticket_item(ticket) -> TicketListItem:
    return TicketListItem(
        ticket_id=ticket.id,
        customer_id=ticket.customer_id,
        subject=ticket.subject,
        category=ticket.category,
        priority=ticket.priority,
        status=ticket.status.value if hasattr(ticket.status, "value") else str(ticket.status),
        current_assignee_id=ticket.current_assignee_id,
        resolved_at=ticket.resolved_at,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def _message_item(message) -> TicketMessageItem:
    return TicketMessageItem(
        message_id=message.id,
        author_id=message.author_id,
        body=message.body,
        visibility=message.visibility,
        created_at=message.created_at,
    )


def _event_item(event) -> TicketEventItem:
    return TicketEventItem(
        event_id=event.id,
        actor_id=event.actor_id,
        event_type=event.event_type,
        from_status=event.from_status.value if hasattr(event.from_status, "value") else event.from_status,
        to_status=event.to_status.value if hasattr(event.to_status, "value") else event.to_status,
        payload_summary=event.payload_summary,
        occurred_at=event.occurred_at,
    )


def _detail_response(request_id: str, ticket, *, include_internal: bool = True) -> TicketDetailResponse:
    return TicketDetailResponse(
        request_id=request_id,
        ticket=_ticket_item(ticket),
        messages=[_message_item(item) for item in sorted(ticket.messages, key=lambda item: item.created_at)
                  if include_internal or item.visibility == "public"],
        events=[_event_item(item) for item in sorted(ticket.events, key=lambda item: item.occurred_at)]
               if include_internal else [],
    )


@router.post("/tickets", response_model=TicketResponse)
async def create_ticket(
    payload: TicketCreateRequest,
    response: Response,
    context: RequestContext = Depends(require_permission(Permission.TICKET_CREATE)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> TicketResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        actor_id = context.scope.actor_id
        assert actor_id is not None
        can_create_all = await uow.identity.has_permission(
            scope=context.scope, user_id=actor_id, permission_code=Permission.TICKET_CREATE_ALL
        )
        if not can_create_all and not await uow.identity.user_has_customer(
            scope=context.scope, user_id=actor_id, customer_id=payload.customer_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "permission_denied", "message": "customer is not associated with the current user"},
            )
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


@router.get("/tickets", response_model=TicketListResponse)
async def list_tickets(
    context: RequestContext = Depends(require_permission(Permission.TICKET_READ)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
    status_filter: str | None = Query(default=None, alias="status", max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
) -> TicketListResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        actor_id = context.scope.actor_id
        assert actor_id is not None
        can_read_all = await uow.identity.has_permission(
            scope=context.scope, user_id=actor_id, permission_code=Permission.TICKET_READ_ALL
        )
        tickets = await uow.support.list_tickets(
            scope=context.scope,
            owner_id=None if can_read_all else actor_id,
            limit=limit,
            status=status_filter,
        )
    return TicketListResponse(
        request_id=context.request_id,
        tickets=[_ticket_item(ticket) for ticket in tickets],
    )


@router.get("/tickets/{ticket_id}", response_model=TicketDetailResponse)
async def get_ticket(
    ticket_id: UUID,
    context: RequestContext = Depends(require_permission(Permission.TICKET_READ)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> TicketDetailResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        actor_id = context.scope.actor_id
        assert actor_id is not None
        can_read_all = await uow.identity.has_permission(
            scope=context.scope, user_id=actor_id, permission_code=Permission.TICKET_READ_ALL
        )
        ticket = await uow.support.get_ticket_detail(
            scope=context.scope,
            ticket_id=ticket_id,
            owner_id=None if can_read_all else actor_id,
        )
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ticket_not_found", "message": "ticket not found"},
        )
    return _detail_response(request_id=context.request_id, ticket=ticket, include_internal=can_read_all)


@router.patch("/tickets/{ticket_id}", response_model=TicketDetailResponse)
async def patch_ticket(
    ticket_id: UUID,
    payload: TicketPatchRequest,
    context: RequestContext = Depends(require_permission(Permission.TICKET_UPDATE)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> TicketDetailResponse:
    has_update = any(
        value is not None
        for value in (
            payload.status,
            payload.subject,
            payload.description_summary,
            payload.priority,
            payload.note,
        )
    )
    if not has_update:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "empty_ticket_update", "message": "at least one update field is required"},
        )

    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        if payload.status:
            await uow.support.update_ticket_status(
                scope=context.scope,
                ticket_id=ticket_id,
                target_status=TicketStatus(payload.status),
                actor_id=context.scope.actor_id,
                reason=payload.note or f"状态更新为 {payload.status}",
            )
        ticket = await uow.support.update_ticket_metadata(
            scope=context.scope,
            ticket_id=ticket_id,
            subject=payload.subject,
            description_summary=payload.description_summary,
            priority=payload.priority,
            note=payload.note,
            actor_id=context.scope.actor_id,
        )
        ticket = await uow.support.get_ticket_detail(
            scope=context.scope,
            ticket_id=ticket_id,
        )
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ticket_not_found", "message": "ticket not found"},
        )
    return _detail_response(request_id=context.request_id, ticket=ticket)


__all__ = ["router"]
