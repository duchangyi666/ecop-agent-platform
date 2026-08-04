from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel

from backend.llm.contracts import ModelUsage


class ModelGateway(Protocol):
    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> tuple[BaseModel, ModelUsage]:
        ...

    def generate_stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[str]:
        ...


__all__ = ["ModelGateway"]
