from __future__ import annotations

from uuid import uuid4

import pytest

from backend.agent.graphs.main_graph import build_main_graph
from backend.agent.nodes.routing import route_from_supervisor
from backend.agent.state import AgentState, create_agent_state
from backend.database.base import TenantScope


def new_state(message: str) -> AgentState:
    return create_agent_state(
        scope=TenantScope(tenant_id=uuid4()),
        request_id=uuid4(),
        message=message,
    )


def state_with_route(route: str) -> AgentState:
    state = new_state("test")
    state.next_action = route
    return state


def test_supervisor_routes_refund_request_to_billing_agent() -> None:
    graph = build_main_graph().compile()

    result = graph.invoke(new_state("我要申请退款"))

    assert result["supervisor_decision"].route == "route_billing"


def test_supervisor_cannot_route_to_unregistered_agent() -> None:
    with pytest.raises(ValueError, match="unsupported route"):
        route_from_supervisor(state_with_route("route_unknown"))
