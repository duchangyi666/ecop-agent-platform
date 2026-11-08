from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.actions import ConversationActionExecutor, action_to_evidence
from backend.agent.agents.customer_service import (
    _MODEL_ERROR_RESPONSE,
    _extract_reply_text,
    _prompt_messages,
)
from backend.agent.graphs.main_graph import build_main_graph
from backend.core.orchestrator import route_intent
from backend.agent.guards import InputSecurityGuard
from backend.agent.nodes.guards import domain_guard_node, input_security_guard_node
from backend.agent.state import AgentState, ConversationMessage, KnowledgeEvidence, create_agent_state
from backend.database.models.support import Conversation, ConversationMessage as StoredConversationMessage
from backend.database.models.governance import MemoryRecord
from backend.database.unit_of_work import UnitOfWork
from backend.domain.common import DomainError
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
    input_restricted: bool = False
    trace_id: UUID | None = None
    audit_event_ids: list[UUID] = field(default_factory=list)


def _decision_value(decision: Any, field_name: str) -> Any:
    if isinstance(decision, dict):
        return decision.get(field_name)
    return getattr(decision, field_name, None)


def _state_value(state: Any, key: str, default=None):
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


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


_REDACTED_INPUT = "[输入因安全检查未保存]"
_INTERRUPTED_REPLY = "回复已中断。请继续说明您的问题。"
_FAILED_REPLY = "处理没有完成，请稍后重试。"


def _history_filters(tenant_id: UUID, conversation_id: UUID, actor_id: UUID):
    return (
        StoredConversationMessage.tenant_id == tenant_id,
        StoredConversationMessage.conversation_id == conversation_id,
        StoredConversationMessage.deleted_at.is_(None),
        StoredConversationMessage.visibility == "public",
        or_(
            and_(
                StoredConversationMessage.role == "user",
                StoredConversationMessage.author_id == actor_id,
                StoredConversationMessage.author_type == "user",
            ),
            and_(
                StoredConversationMessage.role == "assistant",
                StoredConversationMessage.author_id.is_(None),
                StoredConversationMessage.author_type == "agent",
            ),
        ),
    )


async def load_consultation_history(
    session,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    actor_id: UUID,
    limit: int,
) -> list[ConversationMessage]:
    """Restore turns by sequence so equal timestamps and overlapping writes stay paired."""

    filters = _history_filters(tenant_id, conversation_id, actor_id)
    turn_rows = list(
        await session.scalars(
            select(StoredConversationMessage.turn_sequence)
            .where(*filters)
            .group_by(StoredConversationMessage.turn_sequence)
            .order_by(StoredConversationMessage.turn_sequence.desc())
            .limit(limit)
        )
    )
    if not turn_rows:
        return []
    messages = list(
        await session.scalars(
            select(StoredConversationMessage).where(
                *filters,
                StoredConversationMessage.turn_sequence.in_(turn_rows),
            )
        )
    )
    messages.sort(
        key=lambda item: (
            item.turn_sequence,
            0 if item.role == "user" else 1 if item.role == "assistant" else 2,
            item.created_at,
            str(item.id),
        )
    )
    return [ConversationMessage(role=item.role, content=item.body) for item in messages]


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
    HISTORY_MESSAGE_LIMIT = 20

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
        self.turn_cleanup: asyncio.Task[Any] | None = None

    async def run(
        self,
        request: CustomerConsultationWorkflowRequest,
    ) -> CustomerConsultationResult:
        self.turn_cleanup = None
        turn_sequence: int | None = None
        trace_id: UUID | None = None
        conversation_id: UUID | None = None
        assistant_persisted = False
        if self.session_factory is not None:
            request, turn_sequence, trace_id, conversation_id = await self._prepare_persisted_turn(request)
        else:
            request = request.model_copy(
                update={"state": request.state.model_copy(update={"thread_id": request.thread_id})}
            )

        # Guards -> retrieve -> supervisor -> domain tools -> customer-service
        # answer. The user turn is already committed so an SSE cancel can still
        # restore the question.
        graph = build_main_graph(
            self.model_gateway,
            self.session_factory,
            self.event_sink,
            self.knowledge_retriever,
        )
        final_state: Any = None
        try:
            if self.event_sink is not None:
                await self.event_sink("started", {"thread_id": request.thread_id, "status": "started"})
            final_state = await graph.compile().ainvoke(request.state)
            result, evidence, user_message = self._result_from_graph(request, final_state)
            if self.session_factory is not None:
                audit_id, memory_count = await self._persist_completion(
                    request,
                    result,
                    evidence=evidence,
                    user_message=user_message,
                    conversation_id=conversation_id,
                    turn_sequence=turn_sequence,
                    trace_id=trace_id,
                    input_tokens=_state_value(final_state, "total_input_tokens", 0),
                    output_tokens=_state_value(final_state, "total_output_tokens", 0),
                    used_memories=_state_value(final_state, "used_memories", []) or [],
                )
                assistant_persisted = True
                result = replace(
                    result,
                    trace_id=trace_id,
                    audit_event_ids=[audit_id],
                    memory_candidate_count=memory_count,
                )
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
            return result
        except asyncio.CancelledError:
            if conversation_id is not None and not assistant_persisted:
                if final_state is None:
                    self.turn_cleanup = asyncio.create_task(
                        self._close_turn(
                            request,
                            conversation_id=conversation_id,
                            turn_sequence=turn_sequence,
                            trace_id=trace_id,
                            body=_INTERRUPTED_REPLY,
                            trace_status="interrupted",
                            error_summary="client cancelled the consultation stream",
                        )
                    )
                else:
                    result, evidence, user_message = self._result_from_graph(request, final_state)
                    self.turn_cleanup = asyncio.create_task(
                        self._persist_completion(
                            request,
                            result,
                            evidence=evidence,
                            user_message=user_message,
                            conversation_id=conversation_id,
                            turn_sequence=turn_sequence,
                            trace_id=trace_id,
                            input_tokens=_state_value(final_state, "total_input_tokens", 0),
                            output_tokens=_state_value(final_state, "total_output_tokens", 0),
                            used_memories=_state_value(final_state, "used_memories", []) or [],
                        )
                    )
                try:
                    await asyncio.shield(self.turn_cleanup)
                except asyncio.CancelledError:
                    pass
            raise
        except Exception:
            if conversation_id is not None and not assistant_persisted:
                await self._close_turn(
                    request,
                    conversation_id=conversation_id,
                    turn_sequence=turn_sequence,
                    trace_id=trace_id,
                    body=_FAILED_REPLY,
                    trace_status="failed",
                    error_summary="consultation failed before a reply was saved",
                )
            raise

    async def _prepare_persisted_turn(
        self,
        request: CustomerConsultationWorkflowRequest,
    ) -> tuple[CustomerConsultationWorkflowRequest, int, UUID, UUID]:
        scope = request.state.tenant_scope
        if scope.actor_id is None:
            raise DomainError("consultation identity is required")
        user_message = next(
            (message.content for message in reversed(request.state.conversation) if message.role == "user"),
            "",
        )
        restricted = InputSecurityGuard().evaluate(user_message).status in {"block", "human_handoff"}
        persisted_message = _REDACTED_INPUT if restricted else user_message
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            customer_id = await uow.identity.get_customer_for_user(scope=scope, user_id=scope.actor_id)
            statement = (
                insert(Conversation)
                .values(
                    id=uuid4(), tenant_id=scope.tenant_id, user_id=scope.actor_id,
                    customer_id=customer_id, thread_id=request.thread_id,
                    channel="ai_chat", subject="智能客服对话", status="open",
                )
                .on_conflict_do_nothing(constraint="uq_conversations_tenant_id_thread_id")
                .returning(Conversation.id)
            )
            created_conversation = await uow.session.scalar(statement) is not None
            conversation = await uow.support.get_conversation_by_thread(scope=scope, thread_id=request.thread_id)
            if conversation is None or conversation.user_id != scope.actor_id or conversation.channel != "ai_chat":
                raise DomainError("consultation thread is unavailable")
            await uow.support.lock_conversation(scope=scope, conversation_id=conversation.id)
            history = await load_consultation_history(
                uow.session,
                tenant_id=scope.tenant_id,
                conversation_id=conversation.id,
                actor_id=scope.actor_id,
                limit=self.HISTORY_MESSAGE_LIMIT,
            )
            user_row = await uow.support.append_conversation_message(
                scope=scope,
                conversation_id=conversation.id,
                author_id=scope.actor_id,
                author_type="user",
                role="user",
                body=persisted_message[:4000],
                visibility="public",
            )
            if created_conversation:
                conversation.subject = persisted_message[:255] or "智能客服对话"
            trace = await uow.governance.create_runtime_trace(
                scope=scope,
                trace_key=f"{request.thread_id}-{request.state.request_id}",
                entrypoint="agent.customer_consultation",
                input_summary="customer consultation",
                input_hash=hashlib.sha256(
                    f"{request.thread_id}:{request.state.request_id}".encode("utf-8")
                ).hexdigest(),
            )
            turn_sequence = user_row.turn_sequence
            trace_id = trace.id
            conversation_id = conversation.id
        trusted_state = create_agent_state(
            scope=scope,
            request_id=request.state.request_id,
            message=user_message,
            history=history,
            thread_id=request.thread_id,
        )
        prepared = request.model_copy(update={
            "state": request.state.model_copy(update={
                "conversation": trusted_state.conversation,
                "thread_id": request.thread_id,
                "trace_id": trace_id,
            }),
        })
        return prepared, turn_sequence, trace_id, conversation_id

    @staticmethod
    def _result_from_graph(
        request: CustomerConsultationWorkflowRequest,
        final_state: Any,
    ) -> tuple[CustomerConsultationResult, list[Any], str]:
        evidence = _state_value(final_state, "knowledge_evidence", []) or []
        user_message = next(
            (message.content for message in reversed(request.state.conversation) if message.role == "user"),
            "",
        )
        guard_status = _decision_value(_state_value(final_state, "guard_decision"), "status")
        input_restricted = guard_status in {"block", "human_handoff"}
        result = CustomerConsultationResult(
            thread_id=request.thread_id,
            status=_state_value(final_state, "status", "completed"),
            next_action=_state_value(final_state, "next_action", "finish"),
            final_response=_state_value(final_state, "final_response"),
            response_review=_state_value(final_state, "response_review"),
            model_provider=_usage_provider(_state_value(final_state, "model_usage")),
            model_error_code=_error_code(_state_value(final_state, "model_error")),
        )
        return (
            replace(result, knowledge_evidence_count=len(evidence), input_restricted=input_restricted),
            evidence,
            user_message,
        )

    async def _persist_completion(
        self,
        request: CustomerConsultationWorkflowRequest,
        result: CustomerConsultationResult,
        *,
        evidence: list[Any],
        user_message: str,
        conversation_id: UUID | None,
        turn_sequence: int | None,
        trace_id: UUID | None,
        input_tokens: int,
        output_tokens: int,
        used_memories: list[str],
    ) -> tuple[UUID, int]:
        scope = request.state.tenant_scope
        route = self.model_router.resolve(ModelTask.CUSTOMER_SERVICE)
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            memory_records: list[MemoryRecord] = []
            if self.memory_service is not None and not result.input_restricted:
                await self.memory_service.mark_used_in_uow(uow, scope=scope, contents=used_memories)
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
            if result.final_response and conversation_id is not None and turn_sequence is not None:
                await uow.support.append_conversation_message(
                    scope=scope,
                    conversation_id=conversation_id,
                    author_id=None,
                    author_type="agent",
                    role="assistant",
                    body=result.final_response[:4000],
                    visibility="public",
                    turn_sequence=turn_sequence,
                )
            if trace_id is not None:
                await uow.governance.complete_runtime_trace(
                    trace_id=trace_id,
                    status=result.status,
                    error_summary=None,
                    total_input_tokens=input_tokens,
                    total_output_tokens=output_tokens,
                )
        return audit.id, len(memory_records)

    async def _close_turn(
        self,
        request: CustomerConsultationWorkflowRequest,
        *,
        conversation_id: UUID,
        turn_sequence: int | None,
        trace_id: UUID | None,
        body: str,
        trace_status: str,
        error_summary: str,
    ) -> None:
        scope = request.state.tenant_scope
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            if turn_sequence is not None:
                await uow.support.append_conversation_message(
                    scope=scope,
                    conversation_id=conversation_id,
                    author_id=None,
                    author_type="agent",
                    role="assistant",
                    body=body,
                    visibility="public",
                    turn_sequence=turn_sequence,
                )
            if trace_id is not None:
                await uow.governance.complete_runtime_trace(
                    trace_id=trace_id,
                    status=trace_status,
                    error_summary=error_summary,
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
            structured_output=False,
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
        text = _extract_reply_text("".join(accumulated))
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
    "load_consultation_history",
    "run_customer_consultation_graph",
]
