from __future__ import annotations

import hashlib
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.checkpoint import CheckpointStore
from backend.agent.graphs.main_graph import build_main_graph
from backend.agent.policies.risk import RefundPolicyContext, evaluate_refund_policy
from backend.agent.runtime import WorkflowResult
from backend.agent.state import AgentState
from backend.agent.tools.billing import BillingTool, RefundToolRequest
from backend.database.unit_of_work import UnitOfWork


class RefundWorkflowRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    thread_id: str
    state: AgentState
    payment_id: UUID
    amount: Decimal
    refund_idempotency_key: str


def _state_to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _state_to_jsonable(asdict(value))
    if isinstance(value, BaseModel):
        return _state_to_jsonable(value.model_dump(mode="json"))
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _state_to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_state_to_jsonable(item) for item in value]
    return value


class RefundWorkflowService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        checkpoint_store: CheckpointStore | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.checkpoint_store = checkpoint_store

    async def run(self, request: RefundWorkflowRequest) -> WorkflowResult:
        scope = request.state.tenant_scope
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            trace = await uow.governance.create_runtime_trace(
                scope=scope,
                trace_key=f"{request.thread_id}-{uuid4().hex}",
                entrypoint="agent.refund",
                input_summary=f"refund request for payment {request.payment_id}",
                input_hash=hashlib.sha256(
                    f"{request.thread_id}:{request.payment_id}:{request.amount}".encode("utf-8")
                ).hexdigest(),
            )
            graph_result = await build_main_graph().compile().ainvoke(request.state)
            await uow.governance.record_runtime_span(
                trace_id=trace.id,
                node_name="multi_agent_workflow",
                status="succeeded",
                input_summary="structured refund request",
                output_summary=str(graph_result.get("next_action", "finish")),
            )

            billing_tool = BillingTool(uow)
            tool_request = RefundToolRequest(
                scope=scope,
                payment_id=request.payment_id,
                idempotency_key=request.refund_idempotency_key,
                amount=request.amount,
            )
            preview = await billing_tool.preview(tool_request)
            payment = await uow.billing.get_payment_for_tenant(
                scope=scope,
                payment_id=request.payment_id,
            )
            if payment is None:
                raise ValueError("payment disappeared during refund preview")

            await uow.governance.record_tool_execution(
                scope=scope,
                trace_id=trace.id,
                tool_name="billing.preview",
                status="succeeded",
                arguments_summary={"payment_id": str(request.payment_id), "amount": str(request.amount)},
                result_summary={"status": preview.status},
                error_summary=None,
            )
            decision = evaluate_refund_policy(
                RefundPolicyContext(
                    amount=request.amount,
                    payment_amount=payment.amount,
                    actor_type=scope.actor_type or "unknown",
                    payment_status=getattr(payment.status, "value", str(payment.status)),
                    has_unknown_execution=False,
                )
            )

            if not decision.allowed:
                audit = await uow.support.append_audit_log(
                    scope=scope,
                    actor_id=scope.actor_id,
                    action="refund_rejected",
                    resource_type="payment",
                    resource_id=payment.id,
                    metadata={"reason": decision.reason, "amount": str(request.amount)},
                )
                await uow.governance.complete_runtime_trace(
                    trace_id=trace.id,
                    status="rejected",
                    error_summary=decision.reason,
                )
                state = self._state_with_metadata(
                    graph_result,
                    trace_id=trace.id,
                    audit_event_ids=[audit.id],
                    next_action="finish",
                )
                return WorkflowResult(
                    thread_id=request.thread_id,
                    status="rejected",
                    refund_idempotency_key=request.refund_idempotency_key,
                    state=state,
                    trace_id=trace.id,
                    audit_event_ids=[audit.id],
                )

            refund = await billing_tool.request(tool_request)
            tool_audit = await uow.support.append_audit_log(
                scope=scope,
                actor_id=scope.actor_id,
                action="refund_requested",
                resource_type="refund",
                resource_id=refund.id,
                metadata={"amount": str(refund.amount), "status": refund.status.value},
            )
            await uow.governance.record_tool_execution(
                scope=scope,
                trace_id=trace.id,
                tool_name="billing.request",
                status="succeeded",
                arguments_summary={"payment_id": str(request.payment_id), "amount": str(request.amount)},
                result_summary={"refund_id": str(refund.id), "status": refund.status.value},
                error_summary=None,
            )

            audit_event_ids = [tool_audit.id]
            status = "refund_requested"
            approval_request_id: UUID | None = None
            next_action = "finish"
            if decision.requires_approval:
                approval = await uow.support.create_refund_approval_request(
                    scope=scope,
                    refund_id=refund.id,
                    action="approve_refund",
                    payload={
                        "amount": str(request.amount),
                        "payment_id": str(request.payment_id),
                        "refund_id": str(refund.id),
                    },
                    approval_role="finance_manager",
                    checkpoint_reference=request.thread_id,
                )
                approval_request_id = approval.id
                approval_audit = await uow.support.append_audit_log(
                    scope=scope,
                    actor_id=scope.actor_id,
                    action="refund_approval_requested",
                    resource_type="approval_request",
                    resource_id=approval.id,
                    metadata={"refund_id": str(refund.id), "risk": "high"},
                )
                audit_event_ids.append(approval_audit.id)
                status = "awaiting_approval"
                next_action = "human_handoff"

            await uow.governance.save_workflow_checkpoint(
                scope=scope,
                thread_id=request.thread_id,
                state_summary=self._state_to_checkpoint(
                    graph_result,
                    refund_id=refund.id,
                    approval_request_id=approval_request_id,
                    trace_id=trace.id,
                    next_action=next_action,
                ),
                refund_idempotency_key=request.refund_idempotency_key,
                status=status,
                trace_id=trace.id,
            )
            await uow.governance.complete_runtime_trace(
                trace_id=trace.id,
                status="awaiting_approval" if decision.requires_approval else "succeeded",
                error_summary=None,
            )
            state = self._state_with_metadata(
                graph_result,
                trace_id=trace.id,
                audit_event_ids=audit_event_ids,
                next_action=next_action,
                refund_id=refund.id,
                approval_request_id=approval_request_id,
            )
            if self.checkpoint_store is not None:
                await self.checkpoint_store.save(
                    request.thread_id,
                    {
                        "state": state,
                        "refund_idempotency_key": request.refund_idempotency_key,
                        "status": status,
                    },
                )
            return WorkflowResult(
                thread_id=request.thread_id,
                status=status,
                refund_idempotency_key=request.refund_idempotency_key,
                state=state,
                refund_id=refund.id,
                approval_request_id=approval_request_id,
                trace_id=trace.id,
                audit_event_ids=audit_event_ids,
            )

    @staticmethod
    def _state_with_metadata(
        graph_result: dict[str, Any],
        *,
        trace_id: UUID,
        audit_event_ids: list[UUID],
        next_action: str,
        refund_id: UUID | None = None,
        approval_request_id: UUID | None = None,
    ) -> dict[str, Any]:
        state = dict(graph_result)
        state.update(
            {
                "trace_id": trace_id,
                "audit_event_ids": audit_event_ids,
                "next_action": next_action,
            }
        )
        if refund_id is not None:
            state["refund_id"] = refund_id
        if approval_request_id is not None:
            state["approval_request_id"] = approval_request_id
        return state

    @classmethod
    def _state_to_checkpoint(
        cls,
        graph_result: dict[str, Any],
        *,
        refund_id: UUID,
        approval_request_id: UUID | None,
        trace_id: UUID,
        next_action: str,
    ) -> dict[str, Any]:
        state = cls._state_with_metadata(
            graph_result,
            trace_id=trace_id,
            audit_event_ids=[],
            next_action=next_action,
            refund_id=refund_id,
            approval_request_id=approval_request_id,
        )
        return _state_to_jsonable(state)


__all__ = ["RefundWorkflowRequest", "RefundWorkflowService"]
