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


class ChatHistoryItem(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=4000)


class CustomerConsultationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    thread_id: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2000)
    # Optional prior turns so the agent can answer with full conversation
    # context (multi-turn dialogue), not just the latest message.
    history: list[ChatHistoryItem] | None = None


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


class EvaluationRunAgentRequest(BaseModel):
    dataset_code: str = Field(min_length=1, max_length=120)
    kind: Literal["correctness", "guard"] = "correctness"
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


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: UUID | None = None
    user_id: UUID | None = None
    channel: Literal["customer_portal", "email", "chat", "support_workspace"] = "customer_portal"
    subject: str = Field(min_length=1, max_length=255)
    initial_message: str | None = Field(default=None, max_length=4000)


class ConversationMessageCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    role: Literal["user", "agent", "system"] = "user"
    body: str = Field(min_length=1, max_length=4000)
    visibility: Literal["public", "internal"] = "public"


class ConversationMessageItem(BaseModel):
    message_id: UUID
    author_id: UUID | None = None
    author_type: str
    role: str
    body: str
    visibility: str
    created_at: Any = None


class ConversationItem(BaseModel):
    conversation_id: UUID
    customer_id: UUID | None = None
    user_id: UUID | None = None
    channel: str
    subject: str
    status: str
    started_at: Any = None
    resolved_at: Any = None
    message_count: int = 0


class ConversationListResponse(BaseModel):
    request_id: str
    conversations: list[ConversationItem] = Field(default_factory=list)


class ConversationDetailResponse(BaseModel):
    request_id: str
    conversation: ConversationItem
    messages: list[ConversationMessageItem] = Field(default_factory=list)


class TicketListItem(BaseModel):
    ticket_id: UUID
    customer_id: UUID
    subject: str
    category: str | None = None
    priority: str
    status: str
    current_assignee_id: UUID | None = None
    resolved_at: Any = None
    created_at: Any = None
    updated_at: Any = None


class TicketListResponse(BaseModel):
    request_id: str
    tickets: list[TicketListItem] = Field(default_factory=list)


class TicketMessageItem(BaseModel):
    message_id: UUID
    author_id: UUID | None = None
    body: str
    visibility: str
    created_at: Any = None


class TicketEventItem(BaseModel):
    event_id: UUID
    actor_id: UUID | None = None
    event_type: str
    from_status: str | None = None
    to_status: str | None = None
    payload_summary: dict[str, Any] = Field(default_factory=dict)
    occurred_at: Any = None


class TicketDetailResponse(BaseModel):
    request_id: str
    ticket: TicketListItem
    messages: list[TicketMessageItem] = Field(default_factory=list)
    events: list[TicketEventItem] = Field(default_factory=list)


class TicketPatchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    status: str | None = Field(default=None, min_length=1, max_length=50)
    subject: str | None = Field(default=None, min_length=1, max_length=255)
    description_summary: str | None = Field(default=None, max_length=2000)
    priority: Literal["low", "medium", "high", "urgent"] | None = None
    note: str | None = Field(default=None, max_length=2000)


class ApprovalActionItem(BaseModel):
    action_id: UUID
    actor_id: UUID | None = None
    action: str
    reason: str
    changes_summary: dict[str, Any] = Field(default_factory=dict)
    acted_at: Any = None


class ApprovalItem(BaseModel):
    approval_request_id: UUID
    ticket_id: UUID | None = None
    refund_id: UUID | None = None
    action: str
    amount: Any = None
    risk_level: str
    approval_role: str
    status: str
    expires_at: Any = None
    checkpoint_reference: str | None = None
    action_count: int = 0


class ApprovalListResponse(BaseModel):
    request_id: str
    approvals: list[ApprovalItem] = Field(default_factory=list)


class ApprovalDetailResponse(BaseModel):
    request_id: str
    approval: ApprovalItem
    actions: list[ApprovalActionItem] = Field(default_factory=list)


class KnowledgeDocumentListItem(BaseModel):
    document_id: UUID
    external_document_id: str
    title: str
    status: str
    source_uri: str | None = None
    visibility: str
    created_at: Any = None
    updated_at: Any = None


class KnowledgeDocumentListResponse(BaseModel):
    request_id: str
    documents: list[KnowledgeDocumentListItem] = Field(default_factory=list)


class KnowledgeDeleteResponse(BaseModel):
    request_id: str
    document_id: UUID
    status: str
    vector_indexed: bool


class KnowledgeReindexResponse(BaseModel):
    request_id: str
    document_count: int
    chunk_count: int
    vector_indexed: bool


class TenantItem(BaseModel):
    id: UUID
    slug: str
    name: str
    status: str


class TenantListResponse(BaseModel):
    request_id: str
    tenants: list[TenantItem] = Field(default_factory=list)


class IdentityUserItem(BaseModel):
    id: UUID
    email: str
    display_name: str
    status: str
    roles: list[str] = Field(default_factory=list)


class TenantUsersResponse(BaseModel):
    request_id: str
    tenant_id: UUID
    users: list[IdentityUserItem] = Field(default_factory=list)


__all__ = [
    "ApprovalActionItem",
    "ApprovalDetailResponse",
    "ApprovalActionRequest",
    "ApprovalItem",
    "ApprovalListResponse",
    "ConversationCreateRequest",
    "ConversationDetailResponse",
    "ConversationItem",
    "ConversationListResponse",
    "ConversationMessageCreateRequest",
    "ConversationMessageItem",
    "CustomerConsultationRequest",
    "CustomerConsultationResponse",
    "ErrorPayload",
    "ErrorResponse",
    "EvaluationRunItem",
    "EvaluationRunListResponse",
    "EvaluationRunRequest",
    "EvaluationRunResponse",
    "HealthResponse",
    "IdentityUserItem",
    "KnowledgeDocumentResponse",
    "KnowledgeDeleteResponse",
    "TenantItem",
    "TenantListResponse",
    "TenantUsersResponse",
    "KnowledgeDocumentListItem",
    "KnowledgeDocumentListResponse",
    "KnowledgeIngestResponse",
    "KnowledgeReindexResponse",
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
    "TicketDetailResponse",
    "TicketEventItem",
    "TicketCreateRequest",
    "TicketListItem",
    "TicketListResponse",
    "TicketMessageItem",
    "TicketPatchRequest",
    "TicketResponse",
    "WorkflowStatusResponse",
]
