from __future__ import annotations

from backend.agent.contracts import SupervisorDecision
from backend.agent.state import AgentState


def supervisor_node(state: AgentState) -> dict[str, object]:
    message = state.conversation[-1].content.lower() if state.conversation else ""
    if any(keyword in message for keyword in ("退款", "退费", "refund", "账单", "支付")):
        route = "route_billing"
    elif any(keyword in message for keyword in ("知识", "政策", "怎么", "如何")):
        route = "route_knowledge"
    elif any(keyword in message for keyword in ("工单", "投诉", "故障")):
        route = "route_ticket"
    else:
        route = "route_customer"

    decision = SupervisorDecision(route=route, reason="keyword-based structural router")
    return {"supervisor_decision": decision, "next_action": decision.route}


__all__ = ["supervisor_node"]
