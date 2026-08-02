from __future__ import annotations

from uuid import uuid4

import pytest

from backend.database.base import TenantScope


@pytest.mark.asyncio
async def test_runtime_trace_tool_execution_and_checkpoint_are_persisted(uow, tenant_a, tenant_a_user) -> None:
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    trace = await uow.governance.create_runtime_trace(
        scope=scope,
        trace_key=f"trace-{uuid4().hex}",
        entrypoint="agent.refund",
        input_summary="masked refund request",
        input_hash="hash-input",
    )
    execution = await uow.governance.record_tool_execution(
        scope=scope,
        trace_id=trace.id,
        tool_name="billing.preview",
        status="succeeded",
        arguments_summary={"payment_id": "masked"},
        result_summary={"status": "previewed"},
        error_summary=None,
    )
    checkpoint = await uow.governance.save_workflow_checkpoint(
        scope=scope,
        thread_id="thread-persisted-1",
        state_summary={"next_action": "human_handoff"},
        refund_idempotency_key="idem-persisted-1",
        status="awaiting_approval",
        trace_id=trace.id,
    )
    restored = await uow.governance.get_workflow_checkpoint(
        scope=scope,
        thread_id="thread-persisted-1",
    )

    assert execution.trace_id == trace.id
    assert checkpoint.tenant_id == tenant_a.id
    assert restored is not None
    assert restored.state_summary["next_action"] == "human_handoff"


@pytest.mark.asyncio
async def test_runtime_trace_can_be_completed_with_error_summary(uow, tenant_a, tenant_a_user) -> None:
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    trace = await uow.governance.create_runtime_trace(
        scope=scope,
        trace_key=f"trace-error-{uuid4().hex}",
        entrypoint="agent.refund",
        input_summary="masked request",
        input_hash="hash-error",
    )

    completed = await uow.governance.complete_runtime_trace(
        trace_id=trace.id,
        status="failed",
        error_summary="model timeout",
    )

    assert completed.status == "failed"
    assert completed.error_summary == "model timeout"
    assert completed.finished_at is not None
