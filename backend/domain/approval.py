from __future__ import annotations

from enum import Enum

from backend.domain.common import transition_state


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    EXPIRED = "expired"
    MORE_INFORMATION_REQUIRED = "more_information_required"


_APPROVAL_TRANSITIONS = {
    ApprovalStatus.PENDING: frozenset(
        {
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.MODIFIED,
            ApprovalStatus.EXPIRED,
            ApprovalStatus.MORE_INFORMATION_REQUIRED,
        }
    ),
    ApprovalStatus.MORE_INFORMATION_REQUIRED: frozenset({ApprovalStatus.PENDING}),
    ApprovalStatus.MODIFIED: frozenset({ApprovalStatus.PENDING}),
    ApprovalStatus.APPROVED: frozenset(),
    ApprovalStatus.REJECTED: frozenset(),
    ApprovalStatus.EXPIRED: frozenset(),
}


def transition_approval(current: ApprovalStatus, target: ApprovalStatus) -> ApprovalStatus:
    return transition_state(current, target, _APPROVAL_TRANSITIONS)
