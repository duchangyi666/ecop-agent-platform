from __future__ import annotations

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


__all__ = ["ModelGateway"]
