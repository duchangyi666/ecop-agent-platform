import pytest

from backend.domain.common import InvalidStateTransition
from backend.domain.ticket import TicketStatus, transition_ticket


def test_ticket_reopen_requires_resolved_or_closed() -> None:
    with pytest.raises(InvalidStateTransition):
        transition_ticket(TicketStatus.OPEN, TicketStatus.REOPENED)


def test_resolved_ticket_can_reopen() -> None:
    assert transition_ticket(TicketStatus.RESOLVED, TicketStatus.REOPENED) is TicketStatus.REOPENED


def test_closed_ticket_can_reopen() -> None:
    assert transition_ticket(TicketStatus.CLOSED, TicketStatus.REOPENED) is TicketStatus.REOPENED


def test_open_ticket_can_move_to_in_progress() -> None:
    assert transition_ticket(TicketStatus.OPEN, TicketStatus.IN_PROGRESS) is TicketStatus.IN_PROGRESS
