from __future__ import annotations

from decimal import Decimal

from backend.agent.policies.risk import RefundPolicyContext, evaluate_refund_policy
from backend.agent.tools.base import build_default_tool_registry
from backend.agent.graphs.main_graph import build_main_graph
from backend.agent.state import create_agent_state
from backend.database.base import TenantScope
from uuid import uuid4


def refund_context(amount: str = "5000.00") -> RefundPolicyContext:
    return RefundPolicyContext(
        amount=Decimal(amount),
        payment_amount=Decimal("6000.00"),
        actor_type="user",
        payment_status="succeeded",
        has_unknown_execution=False,
    )


def test_high_risk_refund_requires_approval() -> None:
    decision = evaluate_refund_policy(refund_context())

    assert decision.requires_approval is True
    assert decision.allowed is True


def test_low_risk_refund_can_execute_without_approval() -> None:
    decision = evaluate_refund_policy(refund_context("20.00"))

    assert decision.requires_approval is False
    assert decision.allowed is True


def test_unknown_execution_state_is_not_automatically_retryable() -> None:
    context = refund_context("20.00").model_copy(update={"has_unknown_execution": True})

    decision = evaluate_refund_policy(context)

    assert decision.allowed is False
    assert decision.reason == "unknown execution state requires reconciliation"


def test_billing_agent_cannot_access_ticket_tool() -> None:
    registry = build_default_tool_registry()

    assert registry.for_agent("billing").names() == ["billing.preview", "billing.execute"]


async def test_main_graph_routes_billing_to_policy_gate() -> None:
    state = create_agent_state(
        scope=TenantScope(tenant_id=uuid4()),
        request_id=uuid4(),
        message="我要退款",
    )

    result = await build_main_graph().compile().ainvoke(state)

    assert result["supervisor_decision"].route == "route_billing"
