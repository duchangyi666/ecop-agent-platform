from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol


class CheckpointStore(Protocol):
    async def save(self, thread_id: str, state: dict[str, Any]) -> None: ...

    async def load(self, thread_id: str) -> dict[str, Any] | None: ...


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}

    async def save(self, thread_id: str, state: dict[str, Any]) -> None:
        self._states[thread_id] = deepcopy(state)

    async def load(self, thread_id: str) -> dict[str, Any] | None:
        state = self._states.get(thread_id)
        return deepcopy(state) if state is not None else None


__all__ = ["CheckpointStore", "InMemoryCheckpointStore"]
