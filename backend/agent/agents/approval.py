from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.agent.contracts import SpecialistResult
from backend.agent.state import AgentState


def _approval_node(state: AgentState) -> dict[str, object]:
    return {
        "specialist_result": SpecialistResult(
            specialist="approval",
            route="route_approval",
            content="approval material and current status are required",
        ),
        "next_action": "route_approval",
    }


def build_approval_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("approval_agent", _approval_node)
    graph.add_edge(START, "approval_agent")
    graph.add_edge("approval_agent", END)
    return graph


__all__ = ["build_approval_graph"]
