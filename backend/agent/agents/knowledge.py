from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.agent.contracts import SpecialistResult
from backend.agent.state import AgentState


def _knowledge_node(state: AgentState) -> dict[str, object]:
    return {
        "specialist_result": SpecialistResult(
            specialist="knowledge",
            route="route_knowledge",
            content="knowledge retrieval context is required",
        ),
        "next_action": "route_knowledge",
    }


def build_knowledge_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("knowledge_agent", _knowledge_node)
    graph.add_edge(START, "knowledge_agent")
    graph.add_edge("knowledge_agent", END)
    return graph


__all__ = ["build_knowledge_graph"]
