from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.agent.agents.supervisor import supervisor_node
from backend.agent.nodes.normalize import normalize_request
from backend.agent.nodes.routing import route_from_supervisor
from backend.agent.state import AgentState


def build_main_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("normalize_request", normalize_request)
    graph.add_node("supervisor_agent", supervisor_node)
    graph.add_edge(START, "normalize_request")
    graph.add_edge("normalize_request", "supervisor_agent")
    graph.add_conditional_edges(
        "supervisor_agent",
        route_from_supervisor,
        {route: END for route in (
            "route_customer",
            "route_knowledge",
            "route_billing",
            "route_ticket",
            "route_approval",
            "ask_clarification",
            "human_handoff",
            "finish",
        )},
    )
    return graph


__all__ = ["build_main_graph"]
