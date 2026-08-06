from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.agent.actions import ConversationActionExecutor, action_to_evidence
from backend.agent.agents.supervisor import make_supervisor_node
from backend.agent.nodes.guards import (
    domain_guard_node,
    input_security_guard_node,
    route_after_domain,
    route_after_input_security,
)
from backend.agent.policies.risk import policy_gate_node
from backend.agent.state import AgentState
from backend.llm.gateway import ModelGateway

EventSink = Any


def _last_user_message(state: AgentState) -> str:
    for message in reversed(state.conversation):
        if message.role == "user":
            return message.content
    return ""


def _as_graph(async_node) -> Any:
    """Wrap an async node in a compiled subgraph so the main graph supports
    both sync invoke() and async ainvoke()."""
    sub = StateGraph(AgentState)
    sub.add_node("inner", async_node)
    sub.add_edge(START, "inner")
    sub.add_edge("inner", END)
    return sub.compile()


def _make_retrieve_node(session_factory: async_sessionmaker, event_sink: EventSink):
    async def retrieve_node(state: AgentState) -> dict[str, object]:
        from backend.rag.config import get_rag_settings
        from backend.rag.reranker import create_reranker
        from backend.rag.retriever import ConsultationKnowledgeRetriever
        from backend.rag.vector_store import create_knowledge_vector_store

        try:
            retriever = ConsultationKnowledgeRetriever(
                session_factory,
                vector_store=create_knowledge_vector_store(),
                reranker=create_reranker(get_rag_settings()),
            )
            evidence = await retriever.retrieve(
                scope=state.tenant_scope, query=_last_user_message(state), limit=5
            )
        except Exception:  # noqa: BLE001 - retrieval must never break the flow
            evidence = []
        if event_sink is not None:
            await event_sink(
                "evidence",
                {
                    "thread_id": str(state.request_id),
                    "count": len(evidence),
                    "results": [
                        {
                            "document_id": str(item.document_id),
                            "title": item.title,
                            "snippet": (item.content_snippet or "")[:200],
                            "score": item.score,
                            "source": item.source_uri,
                        }
                        for item in evidence
                    ],
                },
            )
        return {"knowledge_evidence": evidence}

    return retrieve_node


def _make_domain_node(
    domain: str,
    session_factory: async_sessionmaker,
    gateway: ModelGateway,
    event_sink: EventSink,
):
    async def domain_node(state: AgentState) -> dict[str, object]:
        executor = ConversationActionExecutor(session_factory)
        action_result, clarification = await executor.run_domain_action(
            gateway,
            state,
            domain=domain,
            user_message=_last_user_message(state),
            thread_id=str(state.request_id),
        )
        if clarification is not None:
            return {
                "final_response": clarification,
                "status": "needs_clarification",
                "next_action": "ask_clarification",
            }
        if action_result is not None:
            if event_sink is not None:
                await event_sink(
                    "action",
                    {
                        "thread_id": str(state.request_id),
                        "action": action_result.action,
                        "summary": action_result.summary,
                    },
                )
            return {
                "knowledge_evidence": [
                    *state.knowledge_evidence,
                    action_to_evidence(action_result),
                ],
                "next_action": "route_customer",
            }
        return {"next_action": "route_customer"}

    return domain_node


def _route_after_domain_agent(state: AgentState) -> str:
    if state.next_action in ("ask_clarification", "human_handoff"):
        return "end"
    return "customer_service"


def build_main_graph(
    model_gateway: ModelGateway | None = None,
    session_factory: async_sessionmaker | None = None,
    event_sink: EventSink = None,
) -> StateGraph:
    from backend.agent.agents.customer_service import build_customer_service_graph

    graph = StateGraph(AgentState)
    graph.add_node("input_security_guard", input_security_guard_node)
    graph.add_node("domain_guard", domain_guard_node)
    graph.add_node("retrieve", _as_graph(_make_retrieve_node(session_factory, event_sink)))
    graph.add_node("supervisor_agent", _as_graph(make_supervisor_node(model_gateway)))
    graph.add_node(
        "customer_service_agent",
        build_customer_service_graph(model_gateway, event_sink).compile(),
    )
    graph.add_node(
        "billing_agent",
        _as_graph(_make_domain_node("route_billing", session_factory, model_gateway, event_sink)),
    )
    graph.add_node(
        "ticket_agent",
        _as_graph(_make_domain_node("route_ticket", session_factory, model_gateway, event_sink)),
    )
    graph.add_node(
        "approval_agent",
        _as_graph(_make_domain_node("route_approval", session_factory, model_gateway, event_sink)),
    )
    graph.add_node("knowledge_agent", lambda state: {"next_action": "route_customer"})
    graph.add_node("policy_gate", policy_gate_node)

    graph.add_edge(START, "input_security_guard")
    graph.add_conditional_edges(
        "input_security_guard",
        route_after_input_security,
        {"domain_guard": "domain_guard", "end": "customer_service_agent"},
    )
    graph.add_conditional_edges(
        "domain_guard",
        route_after_domain,
        {"normalize_request": "retrieve", "end": "customer_service_agent"},
    )
    graph.add_edge("retrieve", "supervisor_agent")
    graph.add_conditional_edges(
        "supervisor_agent",
        lambda state: state.next_action,
        {
            "route_billing": "billing_agent",
            "route_ticket": "ticket_agent",
            "route_approval": "approval_agent",
            "route_knowledge": "knowledge_agent",
            "route_customer": "customer_service_agent",
            "ask_clarification": END,
            "human_handoff": END,
            "finish": END,
        },
    )
    graph.add_conditional_edges(
        "billing_agent",
        _route_after_domain_agent,
        {"customer_service": "policy_gate", "end": END},
    )
    graph.add_edge("policy_gate", "customer_service_agent")
    graph.add_conditional_edges(
        "ticket_agent",
        _route_after_domain_agent,
        {"customer_service": "customer_service_agent", "end": END},
    )
    graph.add_conditional_edges(
        "approval_agent",
        _route_after_domain_agent,
        {"customer_service": "customer_service_agent", "end": END},
    )
    graph.add_edge("knowledge_agent", "customer_service_agent")
    graph.add_edge("customer_service_agent", END)
    return graph


__all__ = ["build_main_graph"]
