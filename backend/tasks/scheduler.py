from __future__ import annotations

import asyncio
import os

from backend.tasks.broker import TaskBroker, create_task_broker
from backend.tasks.config import get_task_settings
from backend.tasks.models import TaskEnvelope


class TaskScheduler:
    def __init__(
        self,
        broker: TaskBroker,
        *,
        interval_seconds: float = 3600.0,
    ) -> None:
        self.broker = broker
        self.interval_seconds = interval_seconds
        self.enqueued_count = 0

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            await self.broker.enqueue(
                TaskEnvelope(
                    task_type="memory.expire",
                    payload={},
                )
            )
            self.enqueued_count += 1
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                pass


async def run_scheduler_forever() -> None:
    settings = get_task_settings()
    scheduler = TaskScheduler(
        create_task_broker(settings),
        interval_seconds=float(os.getenv("SCHEDULER_INTERVAL_SECONDS", "3600")),
    )
    stop_event = asyncio.Event()
    try:
        await scheduler.run_forever(stop_event=stop_event)
    finally:
        await scheduler.broker.close()


def main() -> None:
    asyncio.run(run_scheduler_forever())


if __name__ == "__main__":
    main()


__all__ = ["TaskScheduler", "run_scheduler_forever"]
