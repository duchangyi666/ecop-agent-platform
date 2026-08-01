from __future__ import annotations

import pytest

from backend.agent.runtime import run_refund_workflow
from tests.unit.agent.test_checkpoint_runtime import refund_request


@pytest.mark.asyncio
async def test_multi_agent_refund_workflow_reaches_audited_result() -> None:
    result = await run_refund_workflow(refund_request(), database_url="postgresql+asyncpg://test")

    assert result.status in {"completed", "awaiting_approval"}
    assert result.trace_id is not None
    assert result.audit_event_ids
