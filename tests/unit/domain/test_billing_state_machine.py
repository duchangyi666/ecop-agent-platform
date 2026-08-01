from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from backend.domain.billing import (
    PaymentStatus,
    RefundStatus,
    transition_payment,
    transition_refund,
)
from backend.domain.common import DomainError, InvalidStateTransition, ensure_money, ensure_utc


def test_refund_can_move_from_pending_to_succeeded() -> None:
    assert transition_refund(RefundStatus.PENDING, RefundStatus.SUCCEEDED) is RefundStatus.SUCCEEDED


def test_succeeded_refund_cannot_return_to_pending() -> None:
    with pytest.raises(InvalidStateTransition):
        transition_refund(RefundStatus.SUCCEEDED, RefundStatus.PENDING)


def test_payment_can_move_from_requires_action_to_succeeded() -> None:
    assert transition_payment(PaymentStatus.REQUIRES_ACTION, PaymentStatus.SUCCEEDED) is PaymentStatus.SUCCEEDED


def test_unknown_payment_is_terminal() -> None:
    with pytest.raises(InvalidStateTransition):
        transition_payment(PaymentStatus.UNKNOWN, PaymentStatus.SUCCEEDED)


def test_unknown_refund_execution_state_is_terminal() -> None:
    with pytest.raises(InvalidStateTransition):
        transition_refund(RefundStatus.UNKNOWN_EXECUTION_STATE, RefundStatus.PENDING)


def test_decimal_amount_is_accepted() -> None:
    assert ensure_money(Decimal("10.00")) == Decimal("10.00")


def test_float_amount_is_rejected() -> None:
    with pytest.raises(DomainError):
        ensure_money(10.0)


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(DomainError):
        ensure_utc(datetime(2026, 8, 1, 12, 0, 0))


def test_non_utc_datetime_is_normalized_to_utc() -> None:
    shanghai_time = datetime(2026, 8, 1, 20, 0, 0, tzinfo=timezone(timedelta(hours=8)))

    normalized = ensure_utc(shanghai_time)

    assert normalized == datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert normalized.tzinfo is timezone.utc
