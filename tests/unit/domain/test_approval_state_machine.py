import pytest

from backend.domain.approval import ApprovalStatus, transition_approval
from backend.domain.common import InvalidStateTransition


def test_pending_approval_can_move_to_approved() -> None:
    assert transition_approval(ApprovalStatus.PENDING, ApprovalStatus.APPROVED) is ApprovalStatus.APPROVED


def test_approved_request_cannot_move_to_rejected() -> None:
    with pytest.raises(InvalidStateTransition):
        transition_approval(ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)


def test_more_information_required_can_return_to_pending() -> None:
    assert transition_approval(
        ApprovalStatus.MORE_INFORMATION_REQUIRED,
        ApprovalStatus.PENDING,
    ) is ApprovalStatus.PENDING
