from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.agent.contracts import SpecialistResult
from backend.agent.state import AgentState


def _ticket_node(state: AgentState) -> dict[str, object]:
    return {
        "specialist_result": SpecialistResult(
            specialist="ticket",
            route="route_ticket",
            content="ticket operation requires deterministic repository action",
        ),
        "next_action": "route_ticket",
    }


def build_ticket_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("ticket_agent", _ticket_node)
    graph.add_edge(START, "ticket_agent")
    graph.add_edge("ticket_agent", END)
    return graph


__all__ = ["build_ticket_graph"]
