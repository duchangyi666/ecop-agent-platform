from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.graphs.main_graph import build_main_graph
from backend.agent.guards import InputSecurityGuard
from backend.agent.state import AgentState
from backend.agent.tools.knowledge import (
    KnowledgeDocumentResult,
    KnowledgeSearchRequest,
    KnowledgeTool,
)
from backend.database.unit_of_work import UnitOfWork
from backend.rag.hybrid import merge_document_results
from backend.rag.reranker import KnowledgeDocumentReranker
from backend.rag.vector_store import KnowledgeVectorStore


class KnowledgeWorkflowRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    thread_id: str = Field(min_length=1, max_length=120)
    state: AgentState
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=20)


@dataclass(frozen=True, slots=True)
class KnowledgeWorkflowResult:
    thread_id: str
    status: str
    next_action: str
    final_response: str
    results: list[KnowledgeDocumentResult] = field(default_factory=list)
    trace_id: UUID | None = None
    audit_event_ids: list[UUID] = field(default_factory=list)


def _decision_value(decision: Any, field_name: str) -> Any:
    if isinstance(decision, dict):
        return decision.get(field_name)
    return getattr(decision, field_name, None)


class KnowledgeWorkflowService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        vector_store: KnowledgeVectorStore | None = None,
        document_reranker: KnowledgeDocumentReranker | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.vector_store = vector_store
        self.document_reranker = document_reranker

    async def run(self, request: KnowledgeWorkflowRequest) -> KnowledgeWorkflowResult:
        scope = request.state.tenant_scope
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            trace = await uow.governance.create_runtime_trace(
                scope=scope,
                trace_key=f"{request.thread_id}-{request.state.request_id}",
                entrypoint="agent.knowledge",
                input_summary="knowledge search",
                input_hash=hashlib.sha256(
                    f"{request.thread_id}:{request.state.request_id}".encode("utf-8")
                ).hexdigest(),
            )
            graph_result = await build_main_graph().compile().ainvoke(request.state)
            terminal = self._guard_terminal_outcome(graph_result)
            query_guard = InputSecurityGuard().evaluate(request.query)
            if query_guard.status == "block":
                terminal = (
                    "blocked",
                    "finish",
                    "当前请求未通过安全检查，已阻止知识检索。",
                    "knowledge_security_blocked",
                )
            elif query_guard.status == "human_handoff":
                terminal = (
                    "human_handoff",
                    "human_handoff",
                    "该操作需要人工安全审核。",
                    "knowledge_security_handoff",
                )
            if terminal is not None:
                status, next_action, final_response, audit_action = terminal
                audit = await uow.support.append_audit_log(
                    scope=scope,
                    actor_id=scope.actor_id,
                    action=audit_action,
                    resource_type="knowledge",
                    resource_id=None,
                    metadata={
                        "thread_id": request.thread_id,
                        "workflow_status": status,
                        "next_action": next_action,
                    },
                )
                await uow.governance.complete_runtime_trace(
                    trace_id=trace.id,
                    status=status,
                    error_summary=final_response,
                )
                return KnowledgeWorkflowResult(
                    thread_id=request.thread_id,
                    status=status,
                    next_action=next_action,
                    final_response=final_response,
                    trace_id=trace.id,
                    audit_event_ids=[audit.id],
                )

            tool = KnowledgeTool(uow)
            results: list[KnowledgeDocumentResult] = []
            if self.vector_store is not None:
                vector_hits = await self.vector_store.search(
                    tenant_id=scope.tenant_id,
                    query=request.query,
                    limit=request.limit,
                )
                documents = await uow.knowledge.get_documents_by_ids(
                    scope=scope,
                    document_ids=[hit.document_id for hit in vector_hits],
                )
                documents_by_id = {document.id: document for document in documents}
                seen_document_ids: set[UUID] = set()
                vector_results: list[KnowledgeDocumentResult] = []
                for hit in vector_hits:
                    document = documents_by_id.get(hit.document_id)
                    if document is None or hit.document_id in seen_document_ids:
                        continue
                    seen_document_ids.add(hit.document_id)
                    vector_results.append(
                        KnowledgeDocumentResult(
                            document_id=document.id,
                            title=document.title,
                            external_document_id=document.external_document_id,
                            source_uri=document.source_uri,
                            status=document.status,
                            visibility=document.visibility,
                            content_snippet=hit.content_snippet,
                            score=hit.score,
                        )
                    )
                postgres_results = await tool.search(
                    KnowledgeSearchRequest(
                        scope=scope,
                        query=request.query,
                        limit=request.limit,
                    )
                )
                results = merge_document_results(
                    vector_results,
                    postgres_results,
                    limit=request.limit,
                )
            else:
                results = await tool.search(
                    KnowledgeSearchRequest(
                        scope=scope,
                        query=request.query,
                        limit=request.limit,
                    )
                )
            if self.document_reranker is not None:
                results = await self.document_reranker.rerank(
                    query=request.query,
                    candidates=results,
                )
            final_response = (
                f"已找到 {len(results)} 条知识文档。"
                if results
                else "未找到匹配的知识文档。"
            )
            audit = await uow.support.append_audit_log(
                scope=scope,
                actor_id=scope.actor_id,
                action="knowledge_searched",
                resource_type="knowledge",
                resource_id=None,
                metadata={
                    "thread_id": request.thread_id,
                    "result_count": len(results),
                },
            )
            await uow.governance.record_tool_execution(
                scope=scope,
                trace_id=trace.id,
                tool_name="knowledge.search",
                status="succeeded",
                arguments_summary={"limit": request.limit},
                result_summary={
                    "result_count": len(results),
                    "document_ids": [str(item.document_id) for item in results],
                },
                error_summary=None,
            )
            await uow.governance.complete_runtime_trace(
                trace_id=trace.id,
                status="completed",
                error_summary=None,
            )

        return KnowledgeWorkflowResult(
            thread_id=request.thread_id,
            status="completed",
            next_action="finish",
            final_response=final_response,
            results=results,
            trace_id=trace.id,
            audit_event_ids=[audit.id],
        )

    @staticmethod
    def _guard_terminal_outcome(
        graph_result: dict[str, Any],
    ) -> tuple[str, str, str, str] | None:
        guard_status = _decision_value(graph_result.get("guard_decision"), "status")
        if guard_status != "allow":
            if guard_status == "block":
                return (
                    "blocked",
                    "finish",
                    "当前请求未通过安全检查，已阻止知识检索。",
                    "knowledge_security_blocked",
                )
            return (
                "human_handoff",
                "human_handoff",
                "该操作需要人工安全审核。",
                "knowledge_security_handoff",
            )

        domain_status = _decision_value(graph_result.get("domain_decision"), "status")
        if domain_status != "in_scope":
            if domain_status == "needs_clarification":
                return (
                    "needs_clarification",
                    "ask_clarification",
                    "请补充具体知识库查询场景。",
                    "knowledge_clarification_required",
                )
            return (
                "out_of_scope",
                "finish",
                "请求超出当前平台支持范围。",
                "knowledge_out_of_scope",
            )

        if _decision_value(graph_result.get("domain_decision"), "domain") != "knowledge":
            return (
                "out_of_scope",
                "finish",
                "知识检索接口只处理知识库业务请求。",
                "knowledge_out_of_scope",
            )
        return None


__all__ = [
    "KnowledgeWorkflowRequest",
    "KnowledgeWorkflowResult",
    "KnowledgeWorkflowService",
]
