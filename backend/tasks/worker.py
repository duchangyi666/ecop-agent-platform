from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from backend.database.session import get_session_factory
from backend.tasks.broker import TaskBroker, create_task_broker
from backend.tasks.config import get_task_settings
from backend.tasks.maintenance import expire_memory_records
from backend.tasks.models import TaskEnvelope


TaskHandler = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_memory_expiry(payload: dict[str, Any]) -> None:
    del payload
    expired = await expire_memory_records(get_session_factory())
    if expired:
        print(f"memory expiry: {expired} records")


class TaskWorker:
    def __init__(
        self,
        broker: TaskBroker,
        handlers: dict[str, TaskHandler] | None = None,
        *,
        poll_timeout_seconds: float = 1.0,
    ) -> None:
        self.broker = broker
        self.handlers = handlers or {"memory.expire": handle_memory_expiry}
        self.poll_timeout_seconds = poll_timeout_seconds
        self.processed_count = 0

    async def process_one(self) -> TaskEnvelope | None:
        task = await self.broker.dequeue(self.poll_timeout_seconds)
        if task is None:
            return None
        handler = self.handlers.get(task.task_type)
        if handler is None:
            raise ValueError(f"no handler for task: {task.task_type}")
        await handler(task.payload)
        self.processed_count += 1
        return task

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            await self.process_one()

    async def close(self) -> None:
        await self.broker.close()


async def run_worker_forever() -> None:
    settings = get_task_settings()
    broker = create_task_broker(settings)
    worker = TaskWorker(
        broker,
        poll_timeout_seconds=settings.poll_timeout_seconds,
    )
    stop_event = asyncio.Event()
    try:
        await worker.run_forever(stop_event=stop_event)
    finally:
        await worker.close()


def main() -> None:
    asyncio.run(run_worker_forever())


if __name__ == "__main__":
    main()


__all__ = ["TaskHandler", "TaskWorker", "handle_memory_expiry", "run_worker_forever"]
