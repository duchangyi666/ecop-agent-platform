from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.api.dependencies import get_request_context
from backend.api.schemas import (
    ApprovalActionRequest,
    CustomerConsultationRequest,
    RefundCreateRequest,
)


def test_request_context_rejects_missing_tenant_header() -> None:
    with pytest.raises(HTTPException, match="invalid_tenant_context"):
        get_request_context(
            x_tenant_id=None,
            x_actor_id=str(uuid4()),
            x_actor_type="user",
            x_request_id=None,
        )


def test_request_context_allows_dev_headers_in_dev_mode(monkeypatch) -> None:
    monkeypatch.delenv("AUTH_MODE", raising=False)
    tenant_id = uuid4()
    actor_id = uuid4()

    context = get_request_context(
        x_tenant_id=str(tenant_id),
        x_actor_id=str(actor_id),
        x_actor_type="user",
        x_request_id="req-dev",
    )

    assert context.scope.tenant_id == tenant_id
    assert context.scope.actor_id == actor_id


def test_request_context_rejects_dev_headers_in_oidc_mode(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "oidc")

    with pytest.raises(HTTPException) as exc_info:
        get_request_context(
            x_tenant_id=str(uuid4()),
            x_actor_id=str(uuid4()),
            x_actor_type="user",
            x_request_id="req-oidc",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "authentication_required"


def test_refund_request_requires_positive_amount() -> None:
    with pytest.raises(ValueError):
        RefundCreateRequest(
            thread_id="thread-1",
            payment_id=uuid4(),
            amount="0.00",
            refund_idempotency_key="refund-1",
            message="申请退款",
        )


def test_approval_request_preserves_bounded_reason() -> None:
    request = ApprovalActionRequest(thread_id="thread-1", approved=False, reason="证据不足")

    assert request.reason == "证据不足"


def test_customer_consultation_request_strips_whitespace() -> None:
    request = CustomerConsultationRequest(thread_id="thread-1", message="  客户咨询  ")

    assert request.message == "客户咨询"


def test_customer_consultation_request_rejects_blank_message() -> None:
    with pytest.raises(ValueError):
        CustomerConsultationRequest(thread_id="thread-1", message="   ")
