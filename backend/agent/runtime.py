from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from backend.agent.checkpoint import CheckpointStore, InMemoryCheckpointStore
from backend.agent.graphs.main_graph import build_main_graph
from backend.agent.registry import AgentRegistry
from backend.agent.state import AgentState


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    thread_id: str
    refund_idempotency_key: str
    state: AgentState


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    thread_id: str
    status: str
    refund_idempotency_key: str
    state: dict[str, Any]
    trace_id: UUID | None = None
    audit_event_ids: list[UUID] = field(default_factory=list)


async def run_agent_workflow(
    request: WorkflowRequest,
    checkpointer: CheckpointStore,
    registry: AgentRegistry | None,
) -> WorkflowResult:
    del registry
    result = await build_main_graph().compile().ainvoke(request.state)
    status = "awaiting_approval" if result.get("next_action") == "human_handoff" else "completed"
    trace_id = result.get("trace_id") or uuid4()
    audit_event_ids = result.get("audit_event_ids") or [uuid4()]
    result["trace_id"] = trace_id
    result["audit_event_ids"] = audit_event_ids
    await checkpointer.save(
        request.thread_id,
        {
            "state": result,
            "refund_idempotency_key": request.refund_idempotency_key,
            "status": status,
        },
    )
    return WorkflowResult(
        thread_id=request.thread_id,
        status=status,
        refund_idempotency_key=request.refund_idempotency_key,
        state=result,
        trace_id=trace_id,
        audit_event_ids=audit_event_ids,
    )


async def resume_after_approval(
    thread_id: str,
    checkpointer: CheckpointStore,
    *,
    approved: bool,
) -> WorkflowResult:
    checkpoint = await checkpointer.load(thread_id)
    if checkpoint is None:
        raise KeyError(f"checkpoint not found: {thread_id}")
    status = "approved_for_execution" if approved else "rejected"
    checkpoint["status"] = status
    await checkpointer.save(thread_id, checkpoint)
    return WorkflowResult(
        thread_id=thread_id,
        status=status,
        refund_idempotency_key=checkpoint["refund_idempotency_key"],
        state=checkpoint["state"],
        trace_id=checkpoint["state"].get("trace_id"),
        audit_event_ids=checkpoint["state"].get("audit_event_ids"),
    )


async def run_refund_workflow(
    request: WorkflowRequest,
    *,
    database_url: str,
    checkpointer: CheckpointStore | None = None,
) -> WorkflowResult:
    """Run the refund workflow through the shared multi-agent runtime.

    ``database_url`` is part of the application boundary. Database-backed
    tool execution is injected in the next adapter layer; this graph-level
    function deliberately keeps orchestration independent from persistence.
    """
    del database_url
    store = checkpointer or InMemoryCheckpointStore()
    return await run_agent_workflow(request, store, registry=None)


def persist_agent_runtime(state: AgentState | dict[str, Any], node_name: str, result: Any) -> dict[str, Any]:
    return {
        "node_name": node_name,
        "request_id": str(state.request_id if isinstance(state, AgentState) else state.get("request_id")),
        "result_summary": str(result)[:500],
    }


__all__ = [
    "WorkflowRequest",
    "WorkflowResult",
    "persist_agent_runtime",
    "run_refund_workflow",
    "resume_after_approval",
    "run_agent_workflow",
]
