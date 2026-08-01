from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.agent.contracts import SpecialistResult
from backend.agent.state import AgentState


def _billing_node(state: AgentState) -> dict[str, object]:
    return {
        "specialist_result": SpecialistResult(
            specialist="billing",
            route="route_billing",
            status="needs_policy_gate",
            content="billing context and refund preview are required",
        ),
        "next_action": "route_billing",
    }


def build_billing_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("billing_agent", _billing_node)
    graph.add_edge(START, "billing_agent")
    graph.add_edge("billing_agent", END)
    return graph


__all__ = ["build_billing_graph"]
