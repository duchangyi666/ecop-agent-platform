from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.agent.checkpoint import CheckpointStore
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


async def run_agent_workflow(
    request: WorkflowRequest,
    checkpointer: CheckpointStore,
    registry: AgentRegistry | None,
) -> WorkflowResult:
    del registry
    result = await build_main_graph().compile().ainvoke(request.state)
    status = "awaiting_approval" if result.get("next_action") == "human_handoff" else "completed"
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
    )


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
    "resume_after_approval",
    "run_agent_workflow",
]
