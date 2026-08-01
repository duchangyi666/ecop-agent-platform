from __future__ import annotations

from enum import Enum

from backend.domain.common import transition_state


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PENDING_CUSTOMER = "pending_customer"
    PENDING_APPROVAL = "pending_approval"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"
    CANCELLED = "cancelled"


_TICKET_TRANSITIONS = {
    TicketStatus.OPEN: frozenset(
        {
            TicketStatus.IN_PROGRESS,
            TicketStatus.PENDING_CUSTOMER,
            TicketStatus.PENDING_APPROVAL,
            TicketStatus.ESCALATED,
            TicketStatus.RESOLVED,
            TicketStatus.CANCELLED,
        }
    ),
    TicketStatus.IN_PROGRESS: frozenset(
        {
            TicketStatus.PENDING_CUSTOMER,
            TicketStatus.PENDING_APPROVAL,
            TicketStatus.ESCALATED,
            TicketStatus.RESOLVED,
            TicketStatus.CANCELLED,
        }
    ),
    TicketStatus.PENDING_CUSTOMER: frozenset(
        {
            TicketStatus.IN_PROGRESS,
            TicketStatus.RESOLVED,
            TicketStatus.CANCELLED,
        }
    ),
    TicketStatus.PENDING_APPROVAL: frozenset(
        {
            TicketStatus.IN_PROGRESS,
            TicketStatus.ESCALATED,
            TicketStatus.RESOLVED,
            TicketStatus.CANCELLED,
        }
    ),
    TicketStatus.ESCALATED: frozenset(
        {
            TicketStatus.IN_PROGRESS,
            TicketStatus.PENDING_CUSTOMER,
            TicketStatus.PENDING_APPROVAL,
            TicketStatus.RESOLVED,
            TicketStatus.CANCELLED,
        }
    ),
    TicketStatus.RESOLVED: frozenset({TicketStatus.CLOSED, TicketStatus.REOPENED}),
    TicketStatus.CLOSED: frozenset({TicketStatus.REOPENED}),
    TicketStatus.REOPENED: frozenset(
        {
            TicketStatus.IN_PROGRESS,
            TicketStatus.PENDING_CUSTOMER,
            TicketStatus.PENDING_APPROVAL,
            TicketStatus.ESCALATED,
            TicketStatus.RESOLVED,
            TicketStatus.CANCELLED,
        }
    ),
    TicketStatus.CANCELLED: frozenset(),
}


def transition_ticket(current: TicketStatus, target: TicketStatus) -> TicketStatus:
    return transition_state(current, target, _TICKET_TRANSITIONS)
