from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.actions import ConversationActionExecutor, action_to_evidence
from backend.agent.agents.customer_service import (
    _MODEL_ERROR_RESPONSE,
    _extract_reply_text,
    _prompt_messages,
)
from backend.agent.graphs.main_graph import build_main_graph
from backend.core.orchestrator import route_intent
from backend.agent.nodes.guards import domain_guard_node, input_security_guard_node
from backend.agent.state import AgentState, KnowledgeEvidence
from backend.database.models.governance import MemoryRecord
from backend.database.unit_of_work import UnitOfWork
from backend.llm.contracts import ModelUsage, ResponseDraft
from backend.llm.errors import ModelGatewayError
from backend.llm.gateway import ModelGateway
from backend.llm.router import ModelRouter, ModelTask, create_default_model_router
from backend.llm.safety import ResponseSafetyDecision, ResponseSafetyFilter
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
            "抱歉，我无法协助获取系统配置、内部提示、凭据或未经授权的数据。"
            "我可以继续帮助您处理 CloudDesk 账户、账单、产品支持和工单相关问题。"
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
        # The current user message (the tail of the conversation) drives
        # memory capture and conversation persistence below. It must never
        # be empty for a validated request (message min_length=1).
        user_message = next(
            (m.content for m in reversed(request.state.conversation) if m.role == "user"),
            "",
        )

        if self.event_sink is not None:
            await self.event_sink(
                "started",
                {
                    "thread_id": request.thread_id,
                    "status": "started",
                },
            )

        # The LangGraph main graph is the orchestrator: guards -> retrieve ->
        # supervisor(LLM/classifier routing) -> domain agents(real tools) ->
        # customer-service streamed answer. run() only emits lifecycle events
        # and persists afterwards.
        graph = build_main_graph(
            self.model_gateway, self.session_factory, self.event_sink
        )
        final_state = await graph.compile().ainvoke(request.state)

        def _get(key: str, default=None):
            if isinstance(final_state, dict):
                return final_state.get(key, default)
            return getattr(final_state, key, default)

        evidence = _get("knowledge_evidence", []) or []
        result = CustomerConsultationResult(
            thread_id=request.thread_id,
            status=_get("status", "completed"),
            next_action=_get("next_action", "finish"),
            final_response=_get("final_response"),
            response_review=_get("response_review"),
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

    async def _emit_tokens(self, thread_id: str, text: str) -> None:
        if self.event_sink is None or not text:
            return
        for start in range(0, len(text), 3):
            await self.event_sink(
                "token",
                {"thread_id": thread_id, "text": text[start : start + 3]},
            )

    async def _stream_answer(
        self,
        request: CustomerConsultationWorkflowRequest,
        graph_state: AgentState,
    ) -> CustomerConsultationResult:
        """True token-level streaming of the grounded answer.

        Runs the deterministic guards, then streams the customer-service reply
        from the model (grounded on the retrieved/action evidence), emitting
        token events as they arrive, and finally applies the safety filter.
        """
        state = request.state
        guard = input_security_guard_node(state)["guard_decision"]
        if guard.status != "allow":
            status = "blocked" if guard.status == "block" else "human_handoff"
            message = (
                "抱歉，我无法协助获取系统配置、内部提示、凭据或未经授权的数据。"
                "我可以继续帮助您处理 CloudDesk 账户、账单、产品支持和工单相关问题。"
                if status == "blocked"
                else "该操作需要人工安全审核。"
            )
            return CustomerConsultationResult(
                thread_id=request.thread_id,
                status=status,
                next_action="finish" if status == "blocked" else "human_handoff",
                final_response=message,
                response_review=None,
            )
        domain = domain_guard_node(state)["domain_decision"]
        if domain.status != "in_scope":
            if domain.status == "needs_clarification":
                message = "请补充具体业务场景。"
            else:
                message = "请求超出当前平台支持范围。"
            await self._emit_tokens(request.thread_id, message)
            return CustomerConsultationResult(
                thread_id=request.thread_id,
                status="needs_clarification" if domain.status == "needs_clarification" else "out_of_scope",
                next_action="ask_clarification" if domain.status == "needs_clarification" else "finish",
                final_response=message,
                response_review=None,
            )

        system_prompt, user_prompt = _prompt_messages(
            graph_state.conversation,
            knowledge_evidence=graph_state.knowledge_evidence,
        )
        accumulated: list[str] = []
        try:
            async for token in self.model_gateway.generate_stream(
                system_prompt=system_prompt, user_prompt=user_prompt
            ):
                accumulated.append(token)
                if self.event_sink is not None:
                    await self.event_sink(
                        "token", {"thread_id": request.thread_id, "text": token}
                    )
        except ModelGatewayError:
            return CustomerConsultationResult(
                thread_id=request.thread_id,
                status="human_handoff",
                next_action="human_handoff",
                final_response=_MODEL_ERROR_RESPONSE,
                response_review=None,
            )
        text = _extract_reply_text("".join(accumulated).strip())
        if not text:
            text = "抱歉，我暂时无法生成回复，请稍后再试或联系人工客服。"

        draft = ResponseDraft(answer=text, next_action="finish", confidence=0.8)
        decision = ResponseSafetyFilter().evaluate(
            draft, has_evidence=bool(graph_state.knowledge_evidence)
        )
        if decision.status != "allow":
            return CustomerConsultationResult(
                thread_id=request.thread_id,
                status="human_handoff",
                next_action="human_handoff",
                final_response=decision.response,
                response_review=decision,
            )
        return CustomerConsultationResult(
            thread_id=request.thread_id,
            status="completed",
            next_action="finish",
            final_response=decision.response,
            response_review=decision,
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
