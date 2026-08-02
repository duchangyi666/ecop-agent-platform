from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.agent.agents.approval import build_approval_graph
from backend.agent.agents.supervisor import supervisor_node
from backend.agent.agents.billing import build_billing_graph
from backend.agent.agents.customer_service import build_customer_service_graph
from backend.agent.agents.knowledge import build_knowledge_graph
from backend.agent.agents.ticket import build_ticket_graph
from backend.agent.nodes.normalize import normalize_request
from backend.agent.nodes.routing import route_from_supervisor
from backend.agent.nodes.guards import (
    domain_guard_node,
    input_security_guard_node,
    route_after_domain,
    route_after_input_security,
)
from backend.agent.policies.risk import policy_gate_node
from backend.agent.state import AgentState
from backend.llm.gateway import ModelGateway


def build_main_graph(model_gateway: ModelGateway | None = None) -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("input_security_guard", input_security_guard_node)
    graph.add_node("domain_guard", domain_guard_node)
    graph.add_node("normalize_request", normalize_request)
    graph.add_node("supervisor_agent", supervisor_node)
    graph.add_node(
        "customer_service_agent",
        build_customer_service_graph(model_gateway=model_gateway).compile(),
    )
    graph.add_node("knowledge_agent", build_knowledge_graph().compile())
    graph.add_node("billing_agent", build_billing_graph().compile())
    graph.add_node("ticket_agent", build_ticket_graph().compile())
    graph.add_node("approval_agent", build_approval_graph().compile())
    graph.add_node("policy_gate", policy_gate_node)
    graph.add_edge(START, "input_security_guard")
    graph.add_conditional_edges(
        "input_security_guard",
        route_after_input_security,
        {"domain_guard": "domain_guard", "end": END},
    )
    graph.add_conditional_edges(
        "domain_guard",
        route_after_domain,
        {"normalize_request": "normalize_request", "end": END},
    )
    graph.add_edge("normalize_request", "supervisor_agent")
    graph.add_conditional_edges(
        "supervisor_agent",
        route_from_supervisor,
        {
            "route_billing": "billing_agent",
            "route_customer": "customer_service_agent",
            "route_knowledge": "knowledge_agent",
            "route_ticket": "ticket_agent",
            "route_approval": "approval_agent",
            "ask_clarification": END,
            "human_handoff": END,
            "finish": END,
        },
    )
    graph.add_edge("customer_service_agent", END)
    graph.add_edge("knowledge_agent", END)
    graph.add_edge("ticket_agent", END)
    graph.add_edge("approval_agent", END)
    graph.add_edge("billing_agent", "policy_gate")
    graph.add_edge("policy_gate", END)
    return graph


__all__ = ["build_main_graph"]
