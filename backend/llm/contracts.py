from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ResponseDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str = Field(min_length=1, max_length=4000)
    next_action: Literal["finish", "ask_clarification", "human_handoff"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class ModelUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=160)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    latency_ms: int = Field(ge=0)


class ModelCallError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: Literal[
        "model_not_configured",
        "model_timeout",
        "model_http_error",
        "model_invalid_json",
        "model_invalid_output",
    ]
    retryable: bool
    safe_message: str = Field(min_length=1, max_length=160)


__all__ = ["ModelCallError", "ModelUsage", "ResponseDraft"]
