from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.graphs.main_graph import build_main_graph
from backend.agent.guards import InputSecurityGuard
from backend.agent.state import AgentState
from backend.agent.tools.ticket import (
    TicketCreateRequest,
    TicketTool,
)
from backend.database.unit_of_work import UnitOfWork


class TicketWorkflowRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    thread_id: str = Field(min_length=1, max_length=120)
    state: AgentState
    customer_id: UUID
    subject: str = Field(min_length=1, max_length=255)
    priority: Literal["low", "medium", "high", "urgent"]
    description_summary: str | None = Field(default=None, max_length=2000)
    message: str | None = Field(default=None, max_length=2000)


@dataclass(frozen=True, slots=True)
class TicketWorkflowResult:
    thread_id: str
    status: str
    next_action: str
    final_response: str
    ticket_id: UUID | None = None
    ticket_status: str | None = None
    trace_id: UUID | None = None
    audit_event_ids: list[UUID] = field(default_factory=list)


def _decision_value(decision: Any, field_name: str) -> Any:
    if isinstance(decision, dict):
        return decision.get(field_name)
    return getattr(decision, field_name, None)


class TicketWorkflowService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def run(self, request: TicketWorkflowRequest) -> TicketWorkflowResult:
        scope = request.state.tenant_scope
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            trace = await uow.governance.create_runtime_trace(
                scope=scope,
                trace_key=f"{request.thread_id}-{request.state.request_id}",
                entrypoint="agent.ticket",
                input_summary="ticket workflow",
                input_hash=hashlib.sha256(
                    f"{request.thread_id}:{request.state.request_id}".encode("utf-8")
                ).hexdigest(),
            )
            graph_result = await build_main_graph().compile().ainvoke(request.state)
            terminal = self._guard_terminal_outcome(graph_result)
            message_guard = InputSecurityGuard().evaluate(request.message or "")
            if message_guard.status == "block":
                terminal = (
                    "blocked",
                    "finish",
                    "当前请求未通过安全检查，已阻止工单创建。",
                    "ticket_security_blocked",
                )
            elif message_guard.status == "human_handoff":
                terminal = (
                    "human_handoff",
                    "human_handoff",
                    "该操作需要人工安全审核。",
                    "ticket_security_handoff",
                )
            if terminal is not None:
                status, next_action, final_response, audit_action = terminal
                audit = await uow.support.append_audit_log(
                    scope=scope,
                    actor_id=scope.actor_id,
                    action=audit_action,
                    resource_type="ticket",
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
                return TicketWorkflowResult(
                    thread_id=request.thread_id,
                    status=status,
                    next_action=next_action,
                    final_response=final_response,
                    trace_id=trace.id,
                    audit_event_ids=[audit.id],
                )

            tool = TicketTool(uow)
            created = await tool.create(
                TicketCreateRequest(
                    scope=scope,
                    customer_id=request.customer_id,
                    subject=request.subject,
                    priority=request.priority,
                    description_summary=request.description_summary,
                    message=request.message,
                )
            )
            audit = await uow.support.append_audit_log(
                scope=scope,
                actor_id=scope.actor_id,
                action="ticket_created",
                resource_type="ticket",
                resource_id=created.ticket_id,
                metadata={
                    "thread_id": request.thread_id,
                    "status": created.status,
                    "priority": request.priority,
                },
            )
            await uow.governance.record_tool_execution(
                scope=scope,
                trace_id=trace.id,
                tool_name="ticket.create",
                status="succeeded",
                arguments_summary={
                    "customer_id": str(request.customer_id),
                    "priority": request.priority,
                },
                result_summary={
                    "ticket_id": str(created.ticket_id),
                    "status": created.status,
                },
                error_summary=None,
            )
            await uow.governance.complete_runtime_trace(
                trace_id=trace.id,
                status="ticket_created",
                error_summary=None,
            )

        return TicketWorkflowResult(
            thread_id=request.thread_id,
            status="ticket_created",
            next_action="finish",
            final_response="工单已创建，请通过人工流程继续跟进。",
            ticket_id=created.ticket_id,
            ticket_status=created.status,
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
                    "当前请求未通过安全检查，已阻止工单创建。",
                    "ticket_security_blocked",
                )
            return (
                "human_handoff",
                "human_handoff",
                "该操作需要人工安全审核。",
                "ticket_security_handoff",
            )

        domain_status = _decision_value(graph_result.get("domain_decision"), "status")
        if domain_status != "in_scope":
            if domain_status == "needs_clarification":
                return (
                    "needs_clarification",
                    "ask_clarification",
                    "请补充具体工单业务场景。",
                    "ticket_clarification_required",
                )
            return (
                "out_of_scope",
                "finish",
                "请求超出当前平台支持范围。",
                "ticket_out_of_scope",
            )

        if _decision_value(graph_result.get("domain_decision"), "domain") != "ticket":
            return (
                "out_of_scope",
                "finish",
                "工单接口只处理工单业务请求。",
                "ticket_out_of_scope",
            )
        return None


__all__ = [
    "TicketWorkflowRequest",
    "TicketWorkflowResult",
    "TicketWorkflowService",
]
