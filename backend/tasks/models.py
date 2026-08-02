from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class TaskEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str = Field(default_factory=lambda: uuid4().hex)
    task_type: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


__all__ = ["TaskEnvelope"]
