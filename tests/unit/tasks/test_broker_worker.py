from __future__ import annotations

import asyncio

import pytest

from backend.tasks.broker import InMemoryTaskBroker
from backend.tasks.models import TaskEnvelope
from backend.tasks.scheduler import TaskScheduler
from backend.tasks.worker import TaskWorker


@pytest.mark.asyncio
async def test_in_memory_broker_round_trip() -> None:
    broker = InMemoryTaskBroker()
    task = TaskEnvelope(task_type="memory.expire", payload={})

    await broker.enqueue(task)
    dequeued = await broker.dequeue(timeout_seconds=0.1)

    assert dequeued == task
    assert await broker.dequeue(timeout_seconds=0.01) is None


@pytest.mark.asyncio
async def test_worker_processes_task_with_handler() -> None:
    broker = InMemoryTaskBroker()
    calls: list[str] = []

    async def handler(payload: dict) -> None:
        del payload
        calls.append("ok")

    worker = TaskWorker(
        broker,
        handlers={"test.task": handler},
        poll_timeout_seconds=0.01,
    )
    await broker.enqueue(TaskEnvelope(task_type="test.task", payload={}))

    processed = await worker.process_one()

    assert processed is not None
    assert processed.task_type == "test.task"
    assert calls == ["ok"]
    assert worker.processed_count == 1


@pytest.mark.asyncio
async def test_scheduler_enqueues_memory_expiry_task() -> None:
    broker = InMemoryTaskBroker()
    stop = asyncio.Event()
    scheduler = TaskScheduler(broker, interval_seconds=3600.0)

    task = asyncio.create_task(scheduler.run_forever(stop_event=stop))
    await asyncio.sleep(0.05)
    stop.set()
    await task

    assert scheduler.enqueued_count >= 1
    assert broker.enqueued[0].task_type == "memory.expire"
