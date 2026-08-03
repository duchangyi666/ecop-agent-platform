from __future__ import annotations

from backend.agent.guards import DomainDecision, DomainGuard, InputSecurityGuard
from backend.agent.state import AgentState


def _last_user_message(state: AgentState) -> str:
    for message in reversed(state.conversation):
        if message.role == "user":
            return message.content
    return ""


def _conversation_text(state: AgentState) -> str:
    """Reconstruct the whole dialogue so multi-turn follow-ups ("那要怎么解锁？")
    are classified with their context instead of judged in isolation."""
    parts: list[str] = []
    for message in state.conversation:
        speaker = "用户" if message.role == "user" else "客服"
        parts.append(f"{speaker}：{message.content}")
    return "\n".join(parts)


def input_security_guard_node(state: AgentState) -> dict[str, object]:
    # Security boundary applies to the newest user input.
    return {"guard_decision": InputSecurityGuard().evaluate(_last_user_message(state))}


def domain_guard_node(state: AgentState) -> dict[str, object]:
    # Empty/blank input is routed onward so the normalize node can reject it
    # (classification would otherwise treat the reconstructed "用户：" as
    # needing clarification and bypass the reject path).
    if not _last_user_message(state).strip():
        return {
            "domain_decision": DomainDecision(
                status="in_scope",
                domain="customer_service",
                reason="空输入交由归一化节点处理",
            )
        }
    # Business-scope classification uses the full conversation context.
    return {"domain_decision": DomainGuard().evaluate(_conversation_text(state))}


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
