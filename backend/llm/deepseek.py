from __future__ import annotations

import json
import time
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from backend.llm.config import ModelGatewaySettings
from backend.llm.contracts import ModelCallError, ModelUsage
from backend.llm.errors import ModelGatewayError


class DeepSeekGateway:
    def __init__(
        self,
        settings: ModelGatewaySettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> tuple[BaseModel, ModelUsage]:
        if self.settings.api_key is None:
            raise ModelGatewayError(
                ModelCallError(
                    code="model_not_configured",
                    retryable=False,
                    safe_message="当前智能回复服务未配置",
                )
            )

        api_key = self.settings.api_key.get_secret_value()
        request_body = self._request_body(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
        )
        url = f"{self.settings.base_url.rstrip('/')}/chat/completions"
        last_error: ModelGatewayError | None = None

        for attempt in range(self.settings.max_retries + 1):
            started = time.perf_counter()
            try:
                response = await self._client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                    timeout=self.settings.timeout_seconds,
                )
                if response.status_code >= 500:
                    last_error = ModelGatewayError(
                        ModelCallError(
                            code="model_http_error",
                            retryable=True,
                            safe_message="模型服务暂时不可用",
                        )
                    )
                    if attempt < self.settings.max_retries:
                        continue
                    raise last_error
                if response.status_code >= 400:
                    raise ModelGatewayError(
                        ModelCallError(
                            code="model_http_error",
                            retryable=False,
                            safe_message="模型请求未被接受",
                        )
                    )
                try:
                    payload = response.json()
                except (ValueError, json.JSONDecodeError) as exc:
                    raise ModelGatewayError(
                        ModelCallError(
                            code="model_invalid_json",
                            retryable=False,
                            safe_message="模型返回格式无法解析",
                        )
                    ) from exc
                return self._parse_response(
                    payload,
                    response_model=response_model,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            except ModelGatewayError:
                raise
            except httpx.TimeoutException as exc:
                last_error = ModelGatewayError(
                    ModelCallError(
                        code="model_timeout",
                        retryable=True,
                        safe_message="模型服务响应超时",
                    )
                )
                if attempt >= self.settings.max_retries:
                    raise last_error from exc
            except httpx.TransportError as exc:
                last_error = ModelGatewayError(
                    ModelCallError(
                        code="model_http_error",
                        retryable=True,
                        safe_message="模型服务连接失败",
                    )
                )
                if attempt >= self.settings.max_retries:
                    raise last_error from exc

        if last_error is not None:
            raise last_error
        raise ModelGatewayError(
            ModelCallError(
                code="model_http_error",
                retryable=True,
                safe_message="模型服务调用失败",
            )
        )

    def generate_stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ):
        """True token-level streaming over the OpenAI-compatible SSE endpoint."""

        async def _stream():
            if self.settings.api_key is None:
                raise ModelGatewayError(
                    ModelCallError(
                        code="model_not_configured",
                        retryable=False,
                        safe_message="当前智能回复服务未配置",
                    )
                )
            api_key = self.settings.api_key.get_secret_value()
            body = {
                "model": self.settings.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": True,
                "temperature": 0,
            }
            url = f"{self.settings.base_url.rstrip('/')}/chat/completions"
            async with self._client.stream(
                "POST",
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self.settings.timeout_seconds,
            ) as response:
                if response.status_code >= 400:
                    raise ModelGatewayError(
                        ModelCallError(
                            code="model_http_error",
                            retryable=False,
                            safe_message="模型请求未被接受",
                        )
                    )
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        payload = json.loads(data)
                    except (ValueError, json.JSONDecodeError):
                        continue
                    choices = payload.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content

        return _stream()

    def _request_body(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> dict[str, Any]:
        schema = json.dumps(response_model.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
        return {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "system",
                    "content": f"{system_prompt}\n只输出符合以下 JSON Schema 的 JSON：{schema}",
                },
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "stream": False,
        }

    def _parse_response(
        self,
        payload: Any,
        *,
        response_model: type[BaseModel],
        latency_ms: int,
    ) -> tuple[BaseModel, ModelUsage]:
        try:
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("model content must be string")
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ModelGatewayError(
                ModelCallError(
                    code="model_invalid_json",
                    retryable=False,
                    safe_message="模型返回格式无法解析",
                )
            ) from exc

        try:
            result = response_model.model_validate(parsed)
        except ValidationError as exc:
            raise ModelGatewayError(
                ModelCallError(
                    code="model_invalid_output",
                    retryable=False,
                    safe_message="模型返回内容不符合结构化协议",
                )
            ) from exc

        usage = payload.get("usage") or {}
        return result, ModelUsage(
            provider="deepseek",
            model=self.settings.model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens", usage.get("output_tokens")),
            latency_ms=max(0, latency_ms),
        )


__all__ = ["DeepSeekGateway"]
