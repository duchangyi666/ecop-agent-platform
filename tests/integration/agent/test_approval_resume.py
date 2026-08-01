from __future__ import annotations

from tests.unit.agent.test_checkpoint_runtime import refund_request
from backend.agent.checkpoint import InMemoryCheckpointStore
from backend.agent.runtime import resume_after_approval, run_agent_workflow


async def test_approval_resume_keeps_original_refund_idempotency_key() -> None:
    store = InMemoryCheckpointStore()
    paused = await run_agent_workflow(refund_request(), store, registry=None)
    resumed = await resume_after_approval(paused.thread_id, store, approved=True)

    assert resumed.refund_idempotency_key == "refund-idem-1"
