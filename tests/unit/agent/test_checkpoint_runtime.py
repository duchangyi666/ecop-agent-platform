from __future__ import annotations

from uuid import uuid4

import pytest

from backend.agent.checkpoint import InMemoryCheckpointStore
from backend.agent.runtime import WorkflowRequest, resume_after_approval, run_agent_workflow
from backend.agent.state import create_agent_state
from backend.database.base import TenantScope


def refund_request() -> WorkflowRequest:
    return WorkflowRequest(
        thread_id="thread-refund-1",
        refund_idempotency_key="refund-idem-1",
        state=create_agent_state(
            scope=TenantScope(tenant_id=uuid4()),
            request_id=uuid4(),
            message="我要申请退款",
        ),
    )


@pytest.mark.asyncio
async def test_approval_interrupt_can_resume_with_same_idempotency_key() -> None:
    checkpoint_store = InMemoryCheckpointStore()
    request = refund_request()

    # A paused (awaiting-approval) checkpoint is persisted; resuming must keep
    # the same refund idempotency key so the refund cannot double-execute.
    await checkpoint_store.save(
        request.thread_id,
        {
            "state": {},
            "refund_idempotency_key": request.refund_idempotency_key,
            "status": "awaiting_approval",
        },
    )
    resumed = await resume_after_approval(request.thread_id, checkpoint_store, approved=True)

    assert resumed.status == "approved_for_execution"
    assert resumed.refund_idempotency_key == request.refund_idempotency_key


@pytest.mark.asyncio
async def test_checkpoint_store_returns_none_for_unknown_thread() -> None:
    checkpoint_store = InMemoryCheckpointStore()

    assert await checkpoint_store.load("missing") is None
