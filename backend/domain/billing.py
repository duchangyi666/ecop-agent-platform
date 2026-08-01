from __future__ import annotations

from enum import Enum

from backend.domain.common import transition_state


class PaymentStatus(str, Enum):
    REQUIRES_ACTION = "requires_action"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class RefundStatus(str, Enum):
    REQUESTED = "requested"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"
    UNKNOWN_EXECUTION_STATE = "unknown_execution_state"


_PAYMENT_TRANSITIONS = {
    PaymentStatus.REQUIRES_ACTION: frozenset(
        {PaymentStatus.SUCCEEDED, PaymentStatus.FAILED, PaymentStatus.UNKNOWN}
    ),
    PaymentStatus.UNKNOWN: frozenset(),
    PaymentStatus.SUCCEEDED: frozenset(),
    PaymentStatus.FAILED: frozenset(),
}

_REFUND_TRANSITIONS = {
    RefundStatus.REQUESTED: frozenset(
        {
            RefundStatus.PENDING,
            RefundStatus.REJECTED,
            RefundStatus.FAILED,
            RefundStatus.UNKNOWN_EXECUTION_STATE,
        }
    ),
    RefundStatus.PENDING: frozenset(
        {
            RefundStatus.SUCCEEDED,
            RefundStatus.REJECTED,
            RefundStatus.FAILED,
            RefundStatus.UNKNOWN_EXECUTION_STATE,
        }
    ),
    RefundStatus.SUCCEEDED: frozenset(),
    RefundStatus.REJECTED: frozenset(),
    RefundStatus.FAILED: frozenset(),
    RefundStatus.UNKNOWN_EXECUTION_STATE: frozenset(),
}


def transition_payment(current: PaymentStatus, target: PaymentStatus) -> PaymentStatus:
    return transition_state(current, target, _PAYMENT_TRANSITIONS)


def transition_refund(current: RefundStatus, target: RefundStatus) -> RefundStatus:
    return transition_state(current, target, _REFUND_TRANSITIONS)
