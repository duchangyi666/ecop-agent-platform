from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.actions import ConversationActionExecutor, action_to_evidence
from backend.agent.graphs.main_graph import build_main_graph
from backend.agent.state import AgentState, KnowledgeEvidence
from backend.database.models.governance import MemoryRecord
from backend.database.unit_of_work import UnitOfWork
from backend.llm.contracts import ModelUsage
from backend.llm.gateway import ModelGateway
from backend.llm.router import ModelRouter, ModelTask, create_default_model_router
from backend.llm.safety import ResponseSafetyDecision
from backend.memory.service import MemoryService
from backend.rag.retriever import ConsultationKnowledgeRetriever

EventSink = Callable[[str, dict[str, Any]], Awaitable[None]]


class CustomerConsultationWorkflowRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    thread_id: str = Field(min_length=1, max_length=120)
    state: AgentState


@dataclass(frozen=True, slots=True)
class CustomerConsultationResult:
    thread_id: str
    status: str
    next_action: str | None
    final_response: str | None
    response_review: ResponseSafetyDecision | None
    model_provider: str | None = None
    model_error_code: str | None = None
    knowledge_evidence_count: int = 0
    memory_candidate_count: int = 0
    trace_id: UUID | None = None
    audit_event_ids: list[UUID] = field(default_factory=list)


def _decision_value(decision: Any, field_name: str) -> Any:
    if isinstance(decision, dict):
        return decision.get(field_name)
    return getattr(decision, field_name, None)


def _usage_provider(value: Any) -> str | None:
    if isinstance(value, ModelUsage):
        return value.provider
    if isinstance(value, dict):
        return value.get("provider")
    return getattr(value, "provider", None)


def _error_code(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("code")
    return getattr(value, "code", None)


async def run_customer_consultation_graph(
    *,
    thread_id: str,
    state: AgentState,
    model_gateway: ModelGateway,
) -> CustomerConsultationResult:
    graph_result = await build_main_graph(model_gateway=model_gateway).compile().ainvoke(state)

    guard_status = _decision_value(graph_result.get("guard_decision"), "status")
    if guard_status != "allow":
        status = "blocked" if guard_status == "block" else "human_handoff"
        message = (
            "当前请求未通过安全检查，已阻止模型调用。"
            if status == "blocked"
            else "该操作需要人工安全审核。"
        )
        return CustomerConsultationResult(
            thread_id=thread_id,
            status=status,
            next_action="finish" if status == "blocked" else "human_handoff",
            final_response=message,
            response_review=None,
        )

    domain_status = _decision_value(graph_result.get("domain_decision"), "status")
    if domain_status != "in_scope":
        if domain_status == "needs_clarification":
            return CustomerConsultationResult(
                thread_id=thread_id,
                status="needs_clarification",
                next_action="ask_clarification",
                final_response="请补充具体业务场景。",
                response_review=None,
            )
        return CustomerConsultationResult(
            thread_id=thread_id,
            status="out_of_scope",
            next_action="finish",
            final_response="请求超出当前平台支持范围。",
            response_review=None,
        )

    next_action = graph_result.get("next_action") or "finish"
    final_response = graph_result.get("final_response")
    if not final_response:
        if next_action == "human_handoff":
            final_response = "当前请求将转人工处理。"
        elif next_action == "ask_clarification":
            final_response = "请补充具体业务场景。"
        else:
            final_response = "该请求需要进入对应的业务办理入口，当前仅返回安全说明。"

    status = (
        "human_handoff"
        if next_action == "human_handoff"
        else "needs_clarification"
        if next_action == "ask_clarification"
        else "completed"
    )
    return CustomerConsultationResult(
        thread_id=thread_id,
        status=status,
        next_action=next_action,
        final_response=final_response,
        response_review=graph_result.get("response_review"),
        model_provider=_usage_provider(graph_result.get("model_usage")),
        model_error_code=_error_code(graph_result.get("model_error")),
    )


class CustomerConsultationService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None,
        *,
        model_gateway: ModelGateway,
        knowledge_retriever: ConsultationKnowledgeRetriever | None = None,
        event_sink: EventSink | None = None,
        memory_service: MemoryService | None = None,
        model_router: ModelRouter | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.model_gateway = model_gateway
        self.knowledge_retriever = knowledge_retriever
        self.event_sink = event_sink
        self.memory_service = memory_service
        self.model_router = model_router or create_default_model_router()

    async def run(
        self,
        request: CustomerConsultationWorkflowRequest,
    ) -> CustomerConsultationResult:
        if self.event_sink is not None:
            await self.event_sink(
                "started",
                {
                    "thread_id": request.thread_id,
                    "status": "started",
                },
            )

        evidence: list[KnowledgeEvidence] = []
        graph_state = request.state
        user_message = next(
            (
                message.content
                for message in reversed(request.state.conversation)
                if message.role == "user"
            ),
            "",
        )
        if self.knowledge_retriever is not None:
            evidence = await self.knowledge_retriever.retrieve(
                scope=request.state.tenant_scope,
                query=user_message,
                limit=5,
            )
            if evidence:
                graph_state = request.state.model_copy(
                    update={"knowledge_evidence": evidence},
                )
        if self.event_sink is not None:
            await self.event_sink(
                "evidence",
                {
                    "thread_id": request.thread_id,
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

        # Conversation -> business execution. The model decides whether this
        # turn is a pure question or a real business request; the executor then
        # performs it against PostgreSQL and the outcome is grounded into the
        # answer and surfaced as an evidence card.
        if self.session_factory is not None:
            executor = ConversationActionExecutor(self.session_factory)
            decision = await executor.decide(self.model_gateway, user_message)
            if decision.action != "answer":
                action_result = await executor.execute(
                    scope=request.state.tenant_scope,
                    decision=decision,
                    user_message=user_message,
                    thread_id=request.thread_id,
                )
                if action_result is not None:
                    evidence = [*evidence, action_to_evidence(action_result)]
                    graph_state = request.state.model_copy(
                        update={"knowledge_evidence": evidence}
                    )
                    if self.event_sink is not None:
                        await self.event_sink(
                            "action",
                            {
                                "thread_id": request.thread_id,
                                "action": action_result.action,
                                "summary": action_result.summary,
                            },
                        )

        result = await run_customer_consultation_graph(
            thread_id=request.thread_id,
            state=graph_state,
            model_gateway=self.model_gateway,
        )
        result = replace(result, knowledge_evidence_count=len(evidence))
        if self.event_sink is not None:
            await self.event_sink(
                "completed",
                {
                    "thread_id": request.thread_id,
                    "status": result.status,
                    "next_action": result.next_action,
                    "final_response": result.final_response,
                },
            )
        if self.session_factory is None:
            return result

        scope = request.state.tenant_scope
        route = self.model_router.resolve(ModelTask.CUSTOMER_SERVICE)
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            trace = await uow.governance.create_runtime_trace(
                scope=scope,
                trace_key=f"{request.thread_id}-{request.state.request_id}",
                entrypoint="agent.customer_consultation",
                input_summary="customer consultation",
                input_hash=hashlib.sha256(
                    f"{request.thread_id}:{request.state.request_id}".encode("utf-8")
                ).hexdigest(),
            )
            memory_records: list[MemoryRecord] = []
            if self.memory_service is not None:
                memory_records = await self.memory_service.capture_in_uow(
                    uow,
                    scope=scope,
                    user_id=scope.actor_id,
                    customer_id=request.state.customer_id,
                    message=user_message,
                    response=result.final_response,
                )
            audit = await uow.support.append_audit_log(
                scope=scope,
                actor_id=scope.actor_id,
                action=self._audit_action(result.status),
                resource_type="consultation",
                resource_id=None,
                metadata={
                    "thread_id": request.thread_id,
                    "workflow_status": result.status,
                    "next_action": result.next_action,
                    "response_review_code": (
                        result.response_review.code if result.response_review is not None else None
                    ),
                    "model_provider": result.model_provider,
                    "model_error_code": result.model_error_code,
                    "knowledge_evidence_count": len(evidence),
                    "memory_candidate_count": len(memory_records),
                    "model_route_provider": route.provider,
                    "model_route_model": route.model,
                },
            )
            # Persist the conversation and this turn's messages so dialogue
            # history is a real business record, not only browser state.
            customer_id = request.state.customer_id
            if customer_id is None and scope.actor_id is not None:
                customer_id = await uow.identity.get_customer_for_user(
                    scope=scope, user_id=scope.actor_id
                )
            conversation = await uow.support.get_conversation_by_thread(
                scope=scope, thread_id=request.thread_id
            )
            if conversation is None:
                conversation = await uow.support.create_conversation(
                    scope=scope,
                    customer_id=customer_id,
                    user_id=scope.actor_id,
                    channel="ai_chat",
                    subject=(user_message[:255] or "智能客服对话"),
                )
                conversation.thread_id = request.thread_id
            await uow.support.append_conversation_message(
                scope=scope,
                conversation_id=conversation.id,
                author_id=scope.actor_id,
                author_type="user",
                role="user",
                body=user_message[:4000],
                visibility="public",
            )
            if result.final_response:
                await uow.support.append_conversation_message(
                    scope=scope,
                    conversation_id=conversation.id,
                    author_id=None,
                    author_type="agent",
                    role="assistant",
                    body=result.final_response[:4000],
                    visibility="public",
                )

            await uow.governance.complete_runtime_trace(
                trace_id=trace.id,
                status=result.status,
                error_summary=None,
            )

        return replace(
            result,
            trace_id=trace.id,
            audit_event_ids=[audit.id],
            memory_candidate_count=len(memory_records),
        )

    @staticmethod
    def _audit_action(status: str) -> str:
        return {
            "blocked": "customer_consultation_blocked",
            "out_of_scope": "customer_consultation_out_of_scope",
            "needs_clarification": "customer_consultation_clarification",
            "human_handoff": "customer_consultation_human_handoff",
        }.get(status, "customer_consultation_completed")


__all__ = [
    "CustomerConsultationResult",
    "CustomerConsultationService",
    "CustomerConsultationWorkflowRequest",
    "run_customer_consultation_graph",
]
