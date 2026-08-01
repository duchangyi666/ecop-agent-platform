from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WorkflowError(BaseModel):
    model_config = ConfigDict(frozen=True)

    error_code: str
    node_name: str
    retryable: bool
    error_summary: str

    @classmethod
    def from_exception(cls, node_name: str, exc: Exception) -> "WorkflowError":
        if isinstance(exc, TimeoutError):
            return cls(
                error_code="model_timeout",
                node_name=node_name,
                retryable=True,
                error_summary=str(exc)[:500] or "model call timed out",
            )
        if isinstance(exc, ConnectionError):
            return cls(
                error_code="transient_error",
                node_name=node_name,
                retryable=True,
                error_summary=str(exc)[:500] or "transient connection error",
            )
        return cls(
            error_code="workflow_error",
            node_name=node_name,
            retryable=False,
            error_summary=str(exc)[:500] or exc.__class__.__name__,
        )


class FallbackPolicy:
    @staticmethod
    def next_action(error: WorkflowError, attempts: int) -> str:
        if error.error_code == "unknown_tool_state":
            return "human_handoff"
        if error.retryable and attempts < 3:
            return "retry"
        return "human_handoff"


__all__ = ["FallbackPolicy", "WorkflowError"]
