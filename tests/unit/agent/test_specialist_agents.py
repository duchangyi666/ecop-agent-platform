from __future__ import annotations

from uuid import uuid4

from backend.agent.registry import build_default_registry
from backend.agent.state import create_agent_state
from backend.database.base import TenantScope


def state_for_billing():
    return create_agent_state(
        scope=TenantScope(tenant_id=uuid4()),
        request_id=uuid4(),
        message="客户申请退款",
    )


def test_registry_exposes_five_specialist_agents() -> None:
    registry = build_default_registry()

    assert set(registry.names()) == {"customer_service", "knowledge", "billing", "ticket", "approval"}


def test_billing_agent_returns_structured_specialist_result() -> None:
    billing_agent_graph = build_default_registry().get("billing").graph

    result = billing_agent_graph.invoke(state_for_billing())

    assert result["specialist_result"].agent_name == "billing"
    assert result["specialist_result"].status == "needs_policy_gate"


def test_registry_limits_tools_by_agent() -> None:
    registry = build_default_registry()

    assert registry.get("billing").allowed_tools == ("billing.preview", "billing.execute")
    assert registry.get("ticket").allowed_tools == ("ticket.create", "ticket.update")
