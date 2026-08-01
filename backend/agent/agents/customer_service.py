from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.agent.contracts import SpecialistResult
from backend.agent.state import AgentState


def _customer_service_node(state: AgentState) -> dict[str, object]:
    return {
        "specialist_result": SpecialistResult(
            specialist="customer_service",
            route="route_customer",
            content="customer conversation requires response generation",
        ),
        "next_action": "route_customer",
    }


def build_customer_service_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("customer_service_agent", _customer_service_node)
    graph.add_edge(START, "customer_service_agent")
    graph.add_edge("customer_service_agent", END)
    return graph


__all__ = ["build_customer_service_graph"]
