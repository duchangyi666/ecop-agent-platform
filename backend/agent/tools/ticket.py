from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.database.base import TenantScope
from backend.database.unit_of_work import UnitOfWork
from backend.domain.ticket import TicketStatus


class TicketCreateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    scope: TenantScope
    customer_id: UUID
    subject: str = Field(min_length=1, max_length=255)
    priority: Literal["low", "medium", "high", "urgent"]
    description_summary: str | None = Field(default=None, max_length=2000)
    message: str | None = Field(default=None, max_length=2000)


class TicketUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    scope: TenantScope
    ticket_id: UUID
    target_status: TicketStatus
    actor_id: UUID | None
    reason: str = Field(min_length=1, max_length=500)
    changes: dict[str, Any] = Field(default_factory=dict)


class TicketOperationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticket_id: UUID
    status: str
    subject: str
    message_count: int


class TicketTool:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def create(self, request: TicketCreateRequest) -> TicketOperationResult:
        ticket = await self.uow.support.create_ticket(
            scope=request.scope,
            customer_id=request.customer_id,
            subject=request.subject,
            priority=request.priority,
            description_summary=request.description_summary,
            initial_message=request.message,
        )
        return TicketOperationResult(
            ticket_id=ticket.id,
            status=ticket.status.value,
            subject=ticket.subject,
            message_count=1 if request.message else 0,
        )

    async def update(self, request: TicketUpdateRequest) -> TicketOperationResult:
        ticket = await self.uow.support.update_ticket_status(
            scope=request.scope,
            ticket_id=request.ticket_id,
            target_status=request.target_status,
            actor_id=request.actor_id,
            reason=request.reason,
            changes=request.changes,
        )
        return TicketOperationResult(
            ticket_id=ticket.id,
            status=ticket.status.value,
            subject=ticket.subject,
            message_count=1,
        )


__all__ = [
    "TicketCreateRequest",
    "TicketOperationResult",
    "TicketTool",
    "TicketUpdateRequest",
]
