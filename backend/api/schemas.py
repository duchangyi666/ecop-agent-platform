from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RefundCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    thread_id: str = Field(min_length=1, max_length=120)
    payment_id: UUID
    amount: Decimal = Field(gt=Decimal("0.00"), max_digits=18, decimal_places=2)
    refund_idempotency_key: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2000)


class ApprovalActionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    thread_id: str = Field(min_length=1, max_length=120)
    approved: bool
    reason: str = Field(min_length=1, max_length=500)


class CustomerConsultationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    thread_id: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2000)


class ResponseReviewSummary(BaseModel):
    status: str
    code: str
    reason: str


class CustomerConsultationResponse(BaseModel):
    request_id: str
    thread_id: str
    status: str
    next_action: str | None = None
    final_response: str | None = None
    response_review: ResponseReviewSummary | None = None
    trace_id: UUID | None = None
    audit_event_ids: list[UUID] = Field(default_factory=list)
    model_provider: str | None = None
    model_error_code: str | None = None
    knowledge_evidence_count: int = 0
    memory_candidate_count: int = 0

    @classmethod
    def from_result(
        cls,
        *,
        request_id: str,
        result: Any,
    ) -> "CustomerConsultationResponse":
        review = result.response_review
        return cls(
            request_id=request_id,
            thread_id=result.thread_id,
            status=result.status,
            next_action=result.next_action,
            final_response=result.final_response,
            response_review=(
                ResponseReviewSummary(
                    status=review.status,
                    code=review.code,
                    reason=review.reason,
                )
                if review is not None
                else None
            ),
            trace_id=result.trace_id,
            audit_event_ids=list(result.audit_event_ids),
            model_provider=result.model_provider,
            model_error_code=result.model_error_code,
            knowledge_evidence_count=result.knowledge_evidence_count,
            memory_candidate_count=result.memory_candidate_count,
        )


class TicketCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    thread_id: str = Field(min_length=1, max_length=120)
    customer_id: UUID
    subject: str = Field(min_length=1, max_length=255)
    priority: Literal["low", "medium", "high", "urgent"]
    description_summary: str | None = Field(default=None, max_length=2000)
    message: str | None = Field(default=None, max_length=2000)


class TicketResponse(BaseModel):
    request_id: str
    thread_id: str
    status: str
    next_action: str | None = None
    final_response: str | None = None
    ticket_id: UUID | None = None
    ticket_status: str | None = None
    trace_id: UUID | None = None
    audit_event_ids: list[UUID] = Field(default_factory=list)

    @classmethod
    def from_result(cls, *, request_id: str, result: Any) -> "TicketResponse":
        return cls(
            request_id=request_id,
            thread_id=result.thread_id,
            status=result.status,
            next_action=result.next_action,
            final_response=result.final_response,
            ticket_id=result.ticket_id,
            ticket_status=result.ticket_status,
            trace_id=result.trace_id,
            audit_event_ids=list(result.audit_event_ids),
        )


class KnowledgeDocumentResponse(BaseModel):
    document_id: UUID
    title: str
    external_document_id: str
    source_uri: str | None
    status: str
    visibility: str
    content_snippet: str | None = None
    score: float | None = None


class KnowledgeIngestResponse(BaseModel):
    request_id: str
    thread_id: str
    document_id: UUID
    version_number: int
    chunk_count: int
    vector_indexed: bool
    trace_id: UUID | None = None
    audit_event_ids: list[UUID] = Field(default_factory=list)

    @classmethod
    def from_result(cls, *, request_id: str, result: Any) -> "KnowledgeIngestResponse":
        return cls(
            request_id=request_id,
            thread_id=result.thread_id,
            document_id=result.document_id,
            version_number=result.version_number,
            chunk_count=result.chunk_count,
            vector_indexed=result.vector_indexed,
            trace_id=result.trace_id,
            audit_event_ids=list(result.audit_event_ids),
        )


class KnowledgeSearchResponse(BaseModel):
    request_id: str
    thread_id: str
    status: str
    next_action: str | None = None
    final_response: str | None = None
    results: list[KnowledgeDocumentResponse] = Field(default_factory=list)
    trace_id: UUID | None = None
    audit_event_ids: list[UUID] = Field(default_factory=list)

    @classmethod
    def from_result(cls, *, request_id: str, result: Any) -> "KnowledgeSearchResponse":
        return cls(
            request_id=request_id,
            thread_id=result.thread_id,
            status=result.status,
            next_action=result.next_action,
            final_response=result.final_response,
            results=[
                KnowledgeDocumentResponse(
                    document_id=item.document_id,
                    title=item.title,
                    external_document_id=item.external_document_id,
                    source_uri=item.source_uri,
                    status=item.status,
                    visibility=item.visibility,
                    content_snippet=item.content_snippet,
                    score=item.score,
                )
                for item in result.results
            ],
            trace_id=result.trace_id,
            audit_event_ids=list(result.audit_event_ids),
        )


class RefundResponse(BaseModel):
    request_id: str
    thread_id: str
    status: str
    refund_id: UUID | None = None
    approval_request_id: UUID | None = None
    trace_id: UUID | None = None
    next_action: str | None = None
    reason: str | None = None

    @classmethod
    def from_result(cls, *, request_id: str, result: Any) -> "RefundResponse":
        return cls(
            request_id=request_id,
            thread_id=result.thread_id,
            status=result.status,
            refund_id=result.refund_id,
            approval_request_id=result.approval_request_id,
            trace_id=result.trace_id,
            next_action=result.state.get("next_action"),
            reason=result.state.get("reason"),
        )


class WorkflowStatusResponse(BaseModel):
    request_id: str
    thread_id: str
    status: str
    next_action: str | None = None
    refund_id: UUID | None = None
    approval_request_id: UUID | None = None
    trace_id: UUID | None = None
    has_refund_idempotency_key: bool


class ErrorPayload(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorPayload


class HealthResponse(BaseModel):
    status: str


class RuntimeTraceItem(BaseModel):
    trace_id: UUID
    trace_key: str
    status: str
    entrypoint: str
    started_at: Any = None
    finished_at: Any = None
    total_cost: Any = None
    error_summary: str | None = None


class RuntimeTraceListResponse(BaseModel):
    request_id: str
    traces: list[RuntimeTraceItem] = Field(default_factory=list)


class RuntimeSpanItem(BaseModel):
    span_id: UUID
    node_name: str
    status: str
    input_summary: str
    output_summary: str
    started_at: Any = None
    duration_ms: int | None = None


class RuntimeTraceDetailResponse(BaseModel):
    request_id: str
    trace: RuntimeTraceItem
    spans: list[RuntimeSpanItem] = Field(default_factory=list)


class RuntimeCostResponse(BaseModel):
    request_id: str
    trace_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost: Any = None
    failed_count: int


class RuntimeAgentItem(BaseModel):
    agent_id: UUID
    agent_code: str
    name: str
    status: str


class RuntimeAgentListResponse(BaseModel):
    request_id: str
    agents: list[RuntimeAgentItem] = Field(default_factory=list)


class EvaluationRunRequest(BaseModel):
    dataset_code: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=5, ge=1, le=20)


class EvaluationRunItem(BaseModel):
    run_id: UUID
    dataset_id: UUID
    status: str
    metrics: dict[str, Any]
    started_at: Any = None
    finished_at: Any = None


class EvaluationRunListResponse(BaseModel):
    request_id: str
    runs: list[EvaluationRunItem] = Field(default_factory=list)


class EvaluationRunResponse(BaseModel):
    request_id: str
    run_id: UUID
    dataset_code: str
    case_count: int
    metrics: dict[str, Any]
    status: str = "completed"

    @classmethod
    def from_result(cls, *, request_id: str, result: Any) -> "EvaluationRunResponse":
        return cls(
            request_id=request_id,
            run_id=result.run_id,
            dataset_code=result.dataset_code,
            case_count=result.case_count,
            metrics=result.metrics,
        )


__all__ = [
    "ApprovalActionRequest",
    "CustomerConsultationRequest",
    "CustomerConsultationResponse",
    "ErrorPayload",
    "ErrorResponse",
    "EvaluationRunItem",
    "EvaluationRunListResponse",
    "EvaluationRunRequest",
    "EvaluationRunResponse",
    "HealthResponse",
    "KnowledgeDocumentResponse",
    "KnowledgeIngestResponse",
    "KnowledgeSearchResponse",
    "RefundCreateRequest",
    "RefundResponse",
    "RuntimeAgentItem",
    "RuntimeAgentListResponse",
    "RuntimeCostResponse",
    "RuntimeSpanItem",
    "RuntimeTraceDetailResponse",
    "RuntimeTraceItem",
    "RuntimeTraceListResponse",
    "ResponseReviewSummary",
    "TicketCreateRequest",
    "TicketResponse",
    "WorkflowStatusResponse",
]
