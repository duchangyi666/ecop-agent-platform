from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.runtime import WorkflowResult
from backend.database.base import TenantScope
from backend.database.unit_of_work import UnitOfWork
from backend.domain.approval import ApprovalStatus
from backend.domain.common import DomainError


def _as_uuid(value: Any) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


async def resume_refund_after_approval(
    *,
    database_url: str,
    scope: TenantScope,
    thread_id: str,
    approval_request_id: UUID,
    approved: bool,
    actor_id: UUID | None,
    reason: str | None = None,
) -> WorkflowResult:
    actor_scope = TenantScope(
        tenant_id=scope.tenant_id,
        actor_id=actor_id,
        actor_type=scope.actor_type,
    )
    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with UnitOfWork(session_factory, scope=actor_scope) as uow:
            approval = await uow.support.get_approval_request_for_tenant(
                scope=actor_scope,
                approval_request_id=approval_request_id,
            )
            if approval is None:
                raise DomainError("approval request not found in tenant scope")
            if approval.status is not ApprovalStatus.PENDING:
                raise DomainError("approval request is not pending")

            checkpoint = await uow.governance.get_workflow_checkpoint(
                scope=actor_scope,
                thread_id=thread_id,
            )
            if checkpoint is None:
                raise DomainError("workflow checkpoint not found in tenant scope")

            action = "approved" if approved else "rejected"
            action_reason = reason.strip()[:500] if reason and reason.strip() else "approval action submitted by authorized actor"
            await uow.support.append_approval_action(
                scope=actor_scope,
                approval_request_id=approval_request_id,
                action=action,
                reason=action_reason,
                changes={"thread_id": thread_id},
            )
            status = "approved_for_execution" if approved else "rejected"
            audit = await uow.support.append_audit_log(
                scope=actor_scope,
                actor_id=actor_id,
                action=f"refund_approval_{action}",
                resource_type="approval_request",
                resource_id=approval_request_id,
                metadata={"thread_id": thread_id, "status": status},
            )
            state = dict(checkpoint.state_summary)
            state.update(
                {
                    "next_action": "finish",
                    "approval_request_id": approval_request_id,
                    "refund_id": approval.refund_id,
                    "trace_id": checkpoint.trace_id,
                    "audit_event_ids": [audit.id],
                }
            )
            await uow.governance.save_workflow_checkpoint(
                scope=actor_scope,
                thread_id=thread_id,
                state_summary=state,
                refund_idempotency_key=checkpoint.refund_idempotency_key,
                status=status,
                trace_id=checkpoint.trace_id,
            )
            if checkpoint.trace_id is not None:
                await uow.governance.complete_runtime_trace(
                    trace_id=checkpoint.trace_id,
                    status=status,
                    error_summary=None,
                )
            return WorkflowResult(
                thread_id=thread_id,
                status=status,
                refund_idempotency_key=checkpoint.refund_idempotency_key,
                state=state,
                refund_id=approval.refund_id,
                approval_request_id=approval_request_id,
                trace_id=checkpoint.trace_id,
                audit_event_ids=[audit.id],
            )
    finally:
        await engine.dispose()


__all__ = ["resume_refund_after_approval"]
