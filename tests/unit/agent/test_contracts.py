from __future__ import annotations

import pytest

from backend.agent.contracts import AgentMessage, SpecialistResult, SupervisorDecision, ToolContract
from backend.agent.state import create_agent_state
from tests.unit.agent.helpers import scope, request_id, state_for_message


VALID_ROUTES = (
    "route_customer",
    "route_knowledge",
    "route_billing",
    "route_ticket",
    "route_approval",
    "ask_clarification",
    "human_handoff",
    "finish",
)


def test_supervisor_decision_rejects_unregistered_route() -> None:
    with pytest.raises(ValueError, match="unsupported route"):
        SupervisorDecision(route="route_unknown", reason="bad")


@pytest.mark.parametrize("route", VALID_ROUTES)
def test_supervisor_decision_accepts_registered_routes(route: str) -> None:
    decision = SupervisorDecision(route=route, reason="ok")

    assert decision.route == route
    assert decision.reason == "ok"


def test_agent_state_carries_tenant_scope_and_request_id(scope, request_id) -> None:
    state = create_agent_state(scope=scope, request_id=request_id, message="refund")

    assert state.tenant_scope == scope
    assert state.request_id == request_id
    assert state.conversation[0].content == "refund"


def test_agent_message_keeps_sender_recipient_and_content() -> None:
    message = AgentMessage(sender="supervisor", recipient="billing", content="check refund")

    assert message.sender == "supervisor"
    assert message.recipient == "billing"
    assert message.content == "check refund"


def test_specialist_result_keeps_route_and_content() -> None:
    result = SpecialistResult(route="route_billing", specialist="billing", content="refund approved")

    assert result.route == "route_billing"
    assert result.specialist == "billing"
    assert result.content == "refund approved"


def test_tool_contract_keeps_name_description_and_input_schema() -> None:
    contract = ToolContract(
        name="lookup_customer",
        description="Look up customer context",
        input_schema={"type": "object"},
    )

    assert contract.name == "lookup_customer"
    assert contract.description == "Look up customer context"
    assert contract.input_schema == {"type": "object"}


def test_state_helpers_build_message_backed_state(scope, request_id) -> None:
    state = state_for_message(scope=scope, request_id=request_id, message="need invoice")

    assert state.tenant_scope == scope
    assert state.request_id == request_id
    assert [message.content for message in state.conversation] == ["need invoice"]
