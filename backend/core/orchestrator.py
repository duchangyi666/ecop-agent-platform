"""Orchestrator: intent routing (local classifier -> LLM fallback) + lazy
domain-agent registry, mirroring the reference framework's orchestrator.

The workflow uses :func:`route_intent` to pick a business domain; the registry
exposes ``build_<domain>_graph`` lazily so each domain can grow into its own
``backend/agents/<domain>/`` package without eager imports.
"""

from __future__ import annotations

from typing import Any

from backend.agent.agents.supervisor import route_intent
from backend.agent.state import AgentState
from backend.llm.gateway import ModelGateway

__all__ = ["Orchestrator", "get_orchestrator", "route_intent"]


class Orchestrator:
    """Lazy registry of domain graphs (EduAgent-style), for future growth."""

    def __init__(self) -> None:
        self._graphs: dict[str, Any] = {}

    def _get_graph(self, domain: str) -> Any:
        if domain in self._graphs:
            return self._graphs[domain]
        graph = None
        if domain == "route_billing":
            from backend.agent.agents.billing import build_billing_graph

            graph = build_billing_graph()
        elif domain == "route_ticket":
            from backend.agent.agents.ticket import build_ticket_graph

            graph = build_ticket_graph()
        elif domain == "route_knowledge":
            from backend.agent.agents.knowledge import build_knowledge_graph

            graph = build_knowledge_graph()
        elif domain == "route_approval":
            from backend.agent.agents.approval import build_approval_graph

            graph = build_approval_graph()
        else:
            from backend.agent.agents.customer_service import build_customer_service_graph

            graph = build_customer_service_graph()
        self._graphs[domain] = graph
        return graph


_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


__all__ = ["Orchestrator", "get_orchestrator", "route_intent"]
