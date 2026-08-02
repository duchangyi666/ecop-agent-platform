from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RefundCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    thread_id: str = Field(min_length=1, max_length=120)
    payment_id: UUID
    amount: Decimal = Field(gt=Decimal("0.00"), max_digits=18, decimal_places=2)
    refund_idempotency_key: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2000)


class ApprovalActionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    thread_id: str = Field(min_length=1, max_length=120)
    approved: bool
    reason: str = Field(min_length=1, max_length=500)


class RefundResponse(BaseModel):
    request_id: str
    thread_id: str
    status: str
    refund_id: UUID | None = None
    approval_request_id: UUID | None = None
    trace_id: UUID | None = None
    next_action: str | None = None
    reason: str | None = None

    @classmethod
    def from_result(cls, *, request_id: str, result: Any) -> "RefundResponse":
        return cls(
            request_id=request_id,
            thread_id=result.thread_id,
            status=result.status,
            refund_id=result.refund_id,
            approval_request_id=result.approval_request_id,
            trace_id=result.trace_id,
            next_action=result.state.get("next_action"),
            reason=result.state.get("reason"),
        )


class WorkflowStatusResponse(BaseModel):
    request_id: str
    thread_id: str
    status: str
    next_action: str | None = None
    refund_id: UUID | None = None
    approval_request_id: UUID | None = None
    trace_id: UUID | None = None
    has_refund_idempotency_key: bool


class ErrorPayload(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorPayload


class HealthResponse(BaseModel):
    status: str


__all__ = [
    "ApprovalActionRequest",
    "ErrorPayload",
    "ErrorResponse",
    "HealthResponse",
    "RefundCreateRequest",
    "RefundResponse",
    "WorkflowStatusResponse",
]
