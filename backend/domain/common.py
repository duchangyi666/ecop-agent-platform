from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TypeVar


class DomainError(Exception):
    """Base exception for domain validation failures."""


class InvalidStateTransition(DomainError):
    """Raised when a state machine receives a forbidden transition."""


StateEnum = TypeVar("StateEnum", bound=Enum)


def ensure_money(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal):
        raise DomainError("money values must use Decimal")
    return value


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def transition_state(current: StateEnum, target: StateEnum, allowed: dict[StateEnum, frozenset[StateEnum]]) -> StateEnum:
    if current is target:
        return target
    if target not in allowed.get(current, frozenset()):
        raise InvalidStateTransition(f"cannot transition from {current.value} to {target.value}")
    return target
