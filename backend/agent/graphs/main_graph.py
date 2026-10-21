from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.agent.actions import ConversationActionExecutor, action_to_evidence
from backend.agent.agents.supervisor import make_supervisor_node, supervisor_node
from backend.agent.nodes.guards import (
    domain_guard_node,
    input_security_guard_node,
    route_after_domain,
    route_after_input_security,
)
from backend.agent.contracts import SpecialistResult
from backend.agent.policies.risk import policy_gate_node
from backend.agent.state import AgentState
from backend.llm.contracts import ResponseDraft
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


def _make_retrieve_node(
    session_factory: async_sessionmaker,
    event_sink: EventSink,
    knowledge_retriever=None,
):
    async def retrieve_node(state: AgentState) -> dict[str, object]:
        from backend.rag.config import get_rag_settings
        from backend.rag.reranker import create_reranker
        from backend.rag.retriever import ConsultationKnowledgeRetriever
        from backend.rag.vector_store import create_knowledge_vector_store

        if not _last_user_message(state).strip():
            raise ValueError("conversation cannot be empty")
        try:
            retriever = knowledge_retriever or ConsultationKnowledgeRetriever(
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
        if gateway is None or session_factory is None:
            status = "needs_policy_gate" if domain == "route_billing" else "completed"
            content = {
                "route_billing": "billing context and refund preview are required",
                "route_ticket": "ticket context is ready for customer-service follow-up",
                "route_approval": "approval context is ready for customer-service follow-up",
            }.get(domain, "specialist context is ready for customer-service follow-up")
            return {
                "specialist_result": SpecialistResult(
                    specialist=domain.removeprefix("route_"),
                    route=domain,
                    status=status,
                    content=content,
                ),
                "next_action": "route_customer",
            }
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


def _normalize_request_node(state: AgentState) -> dict[str, object]:
    if not _last_user_message(state).strip():
        raise ValueError("conversation cannot be empty")
    return {}


def _sync_customer_service_node(state: AgentState) -> dict[str, object]:
    """Deterministic fallback for local sync invocations without a model/DB."""

    if state.specialist_result is not None:
        return {
            "final_response": state.specialist_result.content,
            "status": "completed",
            "next_action": "finish",
        }

    if state.guard_decision is not None and state.guard_decision.status != "allow":
        status = "blocked" if state.guard_decision.status == "block" else "human_handoff"
        response = (
            "抱歉，我无法协助获取系统配置、内部提示、凭据或未经授权的数据。"
            if status == "blocked"
            else "该操作需要人工安全审核。"
        )
        return {
            "final_response": response,
            "status": status,
            "next_action": "finish" if status == "blocked" else "human_handoff",
        }
    if state.domain_decision is not None and state.domain_decision.status != "in_scope":
        needs_clarification = state.domain_decision.status == "needs_clarification"
        return {
            "final_response": "请补充具体业务场景。" if needs_clarification else "请求超出当前平台支持范围。",
            "status": "needs_clarification" if needs_clarification else "out_of_scope",
            "next_action": "ask_clarification" if needs_clarification else "finish",
        }

    draft = ResponseDraft(
        answer="您好，我可以协助处理 CloudDesk 账户、账单、产品支持和工单问题。请描述您需要办理的事项。",
        next_action="ask_clarification",
        confidence=0.5,
    )
    return {
        "response_draft": draft,
        "final_response": draft.answer,
        "status": "needs_clarification",
        "next_action": draft.next_action,
        "model_call_count": state.model_call_count + 1,
        "specialist_result": SpecialistResult(
            specialist="customer_service",
            route="route_customer",
            content=draft.answer,
            metadata={"offline_fallback": True},
        ),
    }


def _sync_retrieve_node(state: AgentState) -> dict[str, object]:
    return {"knowledge_evidence": []}


def _build_sync_graph() -> StateGraph:
    """Build the no-dependency graph used by local sync tests and dev startup."""

    graph = StateGraph(AgentState)
    graph.add_node("input_security_guard", input_security_guard_node)
    graph.add_node("domain_guard", domain_guard_node)
    graph.add_node("normalize_request", _normalize_request_node)
    graph.add_node("retrieve", _sync_retrieve_node)
    graph.add_node("supervisor_agent", supervisor_node)
    graph.add_node("customer_service_agent", _sync_customer_service_node)
    graph.add_node("billing_agent", lambda state: {
        "specialist_result": SpecialistResult(
            specialist="billing", route="route_billing", status="needs_policy_gate",
            content="billing context and refund preview are required",
        ),
        "next_action": "route_customer",
    })
    graph.add_node("ticket_agent", lambda state: {
        "specialist_result": SpecialistResult(
            specialist="ticket", route="route_ticket", content="ticket context is ready",
        ),
        "next_action": "route_customer",
    })
    graph.add_node("approval_agent", lambda state: {
        "specialist_result": SpecialistResult(
            specialist="approval", route="route_approval", content="approval context is ready",
        ),
        "next_action": "route_customer",
    })
    graph.add_node("knowledge_agent", lambda state: {
        "specialist_result": SpecialistResult(
            specialist="knowledge", route="route_knowledge", content="knowledge context is ready",
        ),
        "next_action": "route_customer",
    })
    graph.add_node("policy_gate", policy_gate_node)

    graph.add_edge(START, "input_security_guard")
    graph.add_conditional_edges(
        "input_security_guard", route_after_input_security,
        {"domain_guard": "domain_guard", "end": "customer_service_agent"},
    )
    graph.add_conditional_edges(
        "domain_guard", route_after_domain,
        {"normalize_request": "normalize_request", "end": "customer_service_agent"},
    )
    graph.add_edge("normalize_request", "retrieve")
    graph.add_edge("retrieve", "supervisor_agent")
    graph.add_conditional_edges(
        "supervisor_agent", lambda state: state.next_action,
        {
            "route_billing": "billing_agent", "route_ticket": "ticket_agent",
            "route_approval": "approval_agent", "route_knowledge": "knowledge_agent",
            "route_customer": "customer_service_agent", "ask_clarification": END,
            "human_handoff": END, "finish": END,
        },
    )
    graph.add_conditional_edges(
        "billing_agent", _route_after_domain_agent,
        {"customer_service": "policy_gate", "end": END},
    )
    graph.add_conditional_edges(
        "policy_gate",
        lambda state: "end" if state.next_action == "human_handoff" else "customer_service",
        {"end": END, "customer_service": "customer_service_agent"},
    )
    graph.add_conditional_edges(
        "ticket_agent", _route_after_domain_agent,
        {"customer_service": "customer_service_agent", "end": END},
    )
    graph.add_conditional_edges(
        "approval_agent", _route_after_domain_agent,
        {"customer_service": "customer_service_agent", "end": END},
    )
    graph.add_edge("knowledge_agent", "customer_service_agent")
    graph.add_edge("customer_service_agent", END)
    return graph


def build_main_graph(
    model_gateway: ModelGateway | None = None,
    session_factory: async_sessionmaker | None = None,
    event_sink: EventSink = None,
    knowledge_retriever=None,
) -> StateGraph:
    from backend.agent.agents.customer_service import build_customer_service_graph

    if model_gateway is None and session_factory is None and event_sink is None:
        return _build_sync_graph()

    graph = StateGraph(AgentState)
    graph.add_node("input_security_guard", input_security_guard_node)
    graph.add_node("domain_guard", domain_guard_node)
    graph.add_node("normalize_request", _normalize_request_node)
    graph.add_node(
        "retrieve",
        _as_graph(_make_retrieve_node(session_factory, event_sink, knowledge_retriever)),
    )
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
        {"normalize_request": "normalize_request", "end": "customer_service_agent"},
    )
    graph.add_edge("normalize_request", "retrieve")
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
    graph.add_conditional_edges(
        "policy_gate",
        lambda state: "end" if state.next_action == "human_handoff" else "customer_service",
        {"end": END, "customer_service": "customer_service_agent"},
    )
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
