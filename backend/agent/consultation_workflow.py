from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.graphs.main_graph import build_main_graph
from backend.agent.state import AgentState, KnowledgeEvidence
from backend.database.unit_of_work import UnitOfWork
from backend.llm.contracts import ModelUsage
from backend.llm.gateway import ModelGateway
from backend.llm.safety import ResponseSafetyDecision
from backend.rag.retriever import ConsultationKnowledgeRetriever


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
    ) -> None:
        self.session_factory = session_factory
        self.model_gateway = model_gateway
        self.knowledge_retriever = knowledge_retriever

    async def run(
        self,
        request: CustomerConsultationWorkflowRequest,
    ) -> CustomerConsultationResult:
        evidence: list[KnowledgeEvidence] = []
        graph_state = request.state
        if self.knowledge_retriever is not None:
            user_message = next(
                (
                    message.content
                    for message in reversed(request.state.conversation)
                    if message.role == "user"
                ),
                "",
            )
            evidence = await self.knowledge_retriever.retrieve(
                scope=request.state.tenant_scope,
                query=user_message,
                limit=5,
            )
            if evidence:
                graph_state = request.state.model_copy(
                    update={"knowledge_evidence": evidence},
                )

        result = await run_customer_consultation_graph(
            thread_id=request.thread_id,
            state=graph_state,
            model_gateway=self.model_gateway,
        )
        if self.session_factory is None:
            return result

        scope = request.state.tenant_scope
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
                },
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
            knowledge_evidence_count=len(evidence),
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
