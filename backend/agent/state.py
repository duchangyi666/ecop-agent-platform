from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.agent.contracts import SpecialistResult, SupervisorDecision
from backend.database.base import TenantScope


class ConversationMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["user", "assistant", "system", "tool"]
    content: str


class AgentState(BaseModel):
    """Shared state schema used by the LangGraph main graph and subgraphs."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    request_id: UUID
    tenant_scope: TenantScope
    conversation: list[ConversationMessage] = Field(default_factory=list)
    customer_id: UUID | None = None
    next_action: str = "finish"
    supervisor_decision: SupervisorDecision | None = None
    specialist_result: SpecialistResult | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    trace_id: UUID | None = None
    audit_event_ids: list[UUID] = Field(default_factory=list)


def create_agent_state(*, scope: TenantScope, request_id: UUID, message: str) -> AgentState:
    return AgentState(
        request_id=request_id,
        tenant_scope=scope,
        conversation=[ConversationMessage(role="user", content=message)],
    )


__all__ = ["AgentState", "ConversationMessage", "create_agent_state"]
