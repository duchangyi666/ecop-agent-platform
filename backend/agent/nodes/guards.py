from __future__ import annotations

from backend.agent.guards import DomainGuard, InputSecurityGuard
from backend.agent.state import AgentState


def _last_user_message(state: AgentState) -> str:
    for message in reversed(state.conversation):
        if message.role == "user":
            return message.content
    return ""


def input_security_guard_node(state: AgentState) -> dict[str, object]:
    return {"guard_decision": InputSecurityGuard().evaluate(_last_user_message(state))}


def domain_guard_node(state: AgentState) -> dict[str, object]:
    return {"domain_decision": DomainGuard().evaluate(_last_user_message(state))}


def route_after_input_security(state: AgentState) -> str:
    decision = state.guard_decision
    if decision is None:
        raise ValueError("input security guard decision is missing")
    return "domain_guard" if decision.status == "allow" else "end"


def route_after_domain(state: AgentState) -> str:
    decision = state.domain_decision
    if decision is None:
        raise ValueError("domain guard decision is missing")
    return "normalize_request" if decision.status == "in_scope" else "end"


__all__ = [
    "domain_guard_node",
    "input_security_guard_node",
    "route_after_domain",
    "route_after_input_security",
]
