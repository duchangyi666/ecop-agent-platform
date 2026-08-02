from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from backend.agent.refund_workflow import RefundWorkflowRequest, _state_to_jsonable
from backend.agent.state import create_agent_state
from backend.database.base import TenantScope


def test_refund_workflow_request_keeps_payment_fields_structured() -> None:
    scope = TenantScope(tenant_id=uuid4(), actor_type="user")
    state = create_agent_state(
        scope=scope,
        request_id=uuid4(),
        message="我要申请退款",
    )

    request = RefundWorkflowRequest(
        thread_id="thread-refund-service-1",
        state=state,
        payment_id=uuid4(),
        amount=Decimal("20.00"),
        refund_idempotency_key="refund-service-idem-1",
    )

    assert request.amount == Decimal("20.00")
    assert request.payment_id is not None
    assert request.state.conversation[0].content == "我要申请退款"


def test_checkpoint_state_serializes_tenant_scope() -> None:
    tenant_id = uuid4()

    serialized = _state_to_jsonable({"tenant_scope": TenantScope(tenant_id=tenant_id, actor_type="user")})

    assert serialized["tenant_scope"]["tenant_id"] == str(tenant_id)
    assert serialized["tenant_scope"]["actor_type"] == "user"
