from __future__ import annotations

from dataclasses import dataclass

from langgraph.graph.state import CompiledStateGraph

from backend.agent.agents.approval import build_approval_graph
from backend.agent.agents.billing import build_billing_graph
from backend.agent.agents.customer_service import build_customer_service_graph
from backend.agent.agents.knowledge import build_knowledge_graph
from backend.agent.agents.ticket import build_ticket_graph


@dataclass(frozen=True, slots=True)
class AgentRegistration:
    name: str
    graph: CompiledStateGraph
    allowed_tools: tuple[str, ...]


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentRegistration] = {}

    def register(self, name: str, graph: CompiledStateGraph, allowed_tools: tuple[str, ...]) -> None:
        if name in self._agents:
            raise ValueError(f"agent already registered: {name}")
        self._agents[name] = AgentRegistration(name=name, graph=graph, allowed_tools=allowed_tools)

    def get(self, name: str) -> AgentRegistration:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise KeyError(f"agent not registered: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(self._agents)


def build_default_registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register("customer_service", build_customer_service_graph().compile(), ())
    registry.register("knowledge", build_knowledge_graph().compile(), ("knowledge.search",))
    registry.register("billing", build_billing_graph().compile(), ("billing.preview", "billing.execute"))
    registry.register("ticket", build_ticket_graph().compile(), ("ticket.create", "ticket.update"))
    registry.register("approval", build_approval_graph().compile(), ("approval.request", "approval.status"))
    return registry


__all__ = ["AgentRegistration", "AgentRegistry", "build_default_registry"]
