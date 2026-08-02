from __future__ import annotations

from pydantic import BaseModel, ValidationError

from backend.llm.contracts import ModelCallError, ModelUsage
from backend.llm.errors import ModelGatewayError


class FakeModelGateway:
    def __init__(self, response: BaseModel | Exception) -> None:
        self.response = response
        self.call_count = 0

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> tuple[BaseModel, ModelUsage]:
        del system_prompt, user_prompt
        self.call_count += 1
        if isinstance(self.response, Exception):
            raise self.response
        try:
            result = response_model.model_validate(self.response.model_dump(mode="python"))
        except ValidationError as exc:
            raise ModelGatewayError(
                ModelCallError(
                    code="model_invalid_output",
                    retryable=False,
                    safe_message="测试模型返回内容不符合结构化协议",
                )
            ) from exc
        return result, ModelUsage(provider="fake", model="fake", latency_ms=0)


__all__ = ["FakeModelGateway"]
