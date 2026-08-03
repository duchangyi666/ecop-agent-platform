from __future__ import annotations

from backend.agent.contracts import SupervisorDecision
from backend.agent.state import AgentState


def supervisor_node(state: AgentState) -> dict[str, object]:
    message = state.conversation[-1].content.lower() if state.conversation else ""
    # Consultation queries ("how", "what is", "policy") are answered by the
    # customer-service agent with RAG evidence; only concrete operation
    # requests (a refund with a payment reference, etc.) go to billing.
    if any(keyword in message for keyword in ("如何", "怎么", "是什么", "政策", "规则", "为什么", "能否", "可以吗")):
        route = "route_customer"
    elif any(keyword in message for keyword in ("退款", "退费", "refund", "账单", "支付", "扣费")):
        route = "route_billing"
    elif any(keyword in message for keyword in ("工单", "投诉", "故障")):
        route = "route_ticket"
    elif any(keyword in message for keyword in ("审批", "审核", "approval")):
        route = "route_approval"
    else:
        route = "route_customer"

    decision = SupervisorDecision(route=route, reason="keyword-based structural router")
    return {"supervisor_decision": decision, "next_action": decision.route}


__all__ = ["supervisor_node"]
