from __future__ import annotations

import asyncio
import json
from typing import Protocol

from backend.tasks.config import TaskSettings
from backend.tasks.models import TaskEnvelope


class TaskBroker(Protocol):
    async def enqueue(self, task: TaskEnvelope) -> None: ...

    async def dequeue(self, timeout_seconds: float) -> TaskEnvelope | None: ...

    async def close(self) -> None: ...


class InMemoryTaskBroker:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[TaskEnvelope] = asyncio.Queue()
        self.enqueued: list[TaskEnvelope] = []

    async def enqueue(self, task: TaskEnvelope) -> None:
        self.enqueued.append(task)
        await self.queue.put(task)

    async def dequeue(self, timeout_seconds: float) -> TaskEnvelope | None:
        try:
            return await asyncio.wait_for(self.queue.get(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return None

    async def close(self) -> None:
        return None


class RedisTaskBroker:
    def __init__(self, settings: TaskSettings, redis=None) -> None:
        self.settings = settings
        self.redis = redis
        self._owns_redis = redis is None

    async def enqueue(self, task: TaskEnvelope) -> None:
        redis = await self._get_redis()
        await redis.rpush(
            self.settings.queue_name,
            task.model_dump_json(),
        )

    async def dequeue(self, timeout_seconds: float) -> TaskEnvelope | None:
        redis = await self._get_redis()
        result = await redis.blpop(
            self.settings.queue_name,
            timeout=timeout_seconds,
        )
        if result is None:
            return None
        return TaskEnvelope.model_validate_json(result[1])

    async def close(self) -> None:
        if self._owns_redis and self.redis is not None:
            await self.redis.aclose()

    async def _get_redis(self):
        if self.redis is None:
            import redis.asyncio as aioredis

            self.redis = aioredis.from_url(
                self.settings.redis_url,
                decode_responses=True,
            )
        return self.redis


def create_task_broker(
    settings: TaskSettings | None = None,
    *,
    in_memory: bool = False,
) -> TaskBroker:
    resolved = settings or TaskSettings()
    if in_memory:
        return InMemoryTaskBroker()
    return RedisTaskBroker(resolved)


__all__ = [
    "InMemoryTaskBroker",
    "RedisTaskBroker",
    "TaskBroker",
    "create_task_broker",
]
