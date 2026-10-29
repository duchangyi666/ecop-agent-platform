from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.agent.contracts import SpecialistResult, SupervisorDecision
from backend.agent.guards import DomainDecision, GuardDecision, InputSecurityGuard
from backend.database.base import TenantScope
from backend.llm.contracts import ModelCallError, ModelUsage, ResponseDraft


class ConversationMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["user", "assistant", "system", "tool"]
    content: str


class KnowledgeEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: UUID
    external_document_id: str
    title: str
    source_uri: str | None = None
    content_snippet: str | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)


class AgentState(BaseModel):
    """Shared state schema used by the LangGraph main graph and subgraphs."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    request_id: UUID
    tenant_scope: TenantScope
    conversation: list[ConversationMessage] = Field(default_factory=list)
    customer_id: UUID | None = None
    recalled_memories: list[str] = Field(default_factory=list)
    knowledge_evidence: list[KnowledgeEvidence] = Field(default_factory=list)
    status: str = "completed"
    next_action: str = "finish"
    guard_decision: GuardDecision | None = None
    domain_decision: DomainDecision | None = None
    response_draft: ResponseDraft | None = None
    final_response: str | None = None
    model_usage: ModelUsage | None = None
    model_error: ModelCallError | None = None
    response_review: Any | None = None
    model_call_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    supervisor_decision: SupervisorDecision | None = None
    specialist_result: SpecialistResult | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    trace_id: UUID | None = None
    audit_event_ids: list[UUID] = Field(default_factory=list)


def create_agent_state(
    *,
    scope: TenantScope,
    request_id: UUID,
    message: str,
    history: list[ConversationMessage] | None = None,
) -> AgentState:
    """Build agent state. `history` carries prior turns so the model can
    answer with multi-turn context; the current user message is appended."""
    guard = InputSecurityGuard()
    conversation = [
        item.model_copy(update={"content": "[历史内容因安全检查已隐藏]"})
        if guard.evaluate(item.content).status != "allow" else item
        for item in history or []
    ]
    conversation.append(ConversationMessage(role="user", content=message))
    return AgentState(
        request_id=request_id,
        tenant_scope=scope,
        conversation=conversation,
    )


__all__ = ["AgentState", "ConversationMessage", "KnowledgeEvidence", "create_agent_state"]
