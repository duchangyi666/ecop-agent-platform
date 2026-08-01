from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.agent.agents.supervisor import supervisor_node
from backend.agent.agents.billing import build_billing_graph
from backend.agent.nodes.normalize import normalize_request
from backend.agent.nodes.routing import route_from_supervisor
from backend.agent.policies.risk import policy_gate_node
from backend.agent.state import AgentState


def build_main_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("normalize_request", normalize_request)
    graph.add_node("supervisor_agent", supervisor_node)
    graph.add_node("billing_agent", build_billing_graph().compile())
    graph.add_node("policy_gate", policy_gate_node)
    graph.add_edge(START, "normalize_request")
    graph.add_edge("normalize_request", "supervisor_agent")
    graph.add_conditional_edges(
        "supervisor_agent",
        route_from_supervisor,
        {
            "route_billing": "billing_agent",
            "route_customer": END,
            "route_knowledge": END,
            "route_ticket": END,
            "route_approval": END,
            "ask_clarification": END,
            "human_handoff": END,
            "finish": END,
        },
    )
    graph.add_edge("billing_agent", "policy_gate")
    graph.add_edge("policy_gate", END)
    return graph


__all__ = ["build_main_graph"]
