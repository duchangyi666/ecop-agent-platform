from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field


class TaskSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    redis_url: str = Field(default="redis://localhost:16380/0")
    queue_name: str = Field(default="ecop:tasks")
    poll_timeout_seconds: float = Field(default=1.0, gt=0.0)


def get_task_settings() -> TaskSettings:
    return TaskSettings(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:16380/0"),
        queue_name=os.getenv("TASK_QUEUE_NAME", "ecop:tasks"),
        poll_timeout_seconds=float(os.getenv("TASK_POLL_TIMEOUT_SECONDS", "1")),
    )


__all__ = ["TaskSettings", "get_task_settings"]
