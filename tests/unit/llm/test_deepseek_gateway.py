from __future__ import annotations

import json

import httpx
import pytest

from backend.llm.config import ModelGatewaySettings
from backend.llm.contracts import ResponseDraft
from backend.llm.deepseek import DeepSeekGateway
from backend.llm.errors import ModelGatewayError
from backend.llm.fake import FakeModelGateway


def _settings(*, api_key: str | None = "test-key", max_retries: int = 1) -> ModelGatewaySettings:
    return ModelGatewaySettings(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        max_retries=max_retries,
    )


def _success_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": "您好",
                                "next_action": "finish",
                                "confidence": 0.8,
                                "evidence_ids": [],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8},
        },
    )


@pytest.mark.asyncio
async def test_deepseek_gateway_sends_json_request_and_parses_response() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _success_response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = DeepSeekGateway(_settings(), client=client)
        result, usage = await gateway.generate_structured(
            system_prompt="system",
            user_prompt="hello",
            response_model=ResponseDraft,
        )

    assert result.answer == "您好"
    assert usage.input_tokens == 12
    assert usage.output_tokens == 8
    assert requests[0].url.path == "/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer test-key"
    body = json.loads(requests[0].content)
    assert body["model"] == "deepseek-v4-flash"
    assert body["response_format"] == {"type": "json_object"}
    assert body["stream"] is False


@pytest.mark.asyncio
async def test_missing_api_key_does_not_create_http_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = DeepSeekGateway(_settings(api_key=None), client=client)
        with pytest.raises(ModelGatewayError) as exc_info:
            await gateway.generate_structured(
                system_prompt="system",
                user_prompt="hello",
                response_model=ResponseDraft,
            )

    assert exc_info.value.error.code == "model_not_configured"


@pytest.mark.asyncio
async def test_server_error_is_retried_once() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503) if attempts == 1 else _success_response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result, _ = await DeepSeekGateway(_settings(), client=client).generate_structured(
            system_prompt="system",
            user_prompt="hello",
            response_model=ResponseDraft,
        )

    assert attempts == 2
    assert result.answer == "您好"


@pytest.mark.asyncio
async def test_client_error_is_not_retried() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelGatewayError) as exc_info:
            await DeepSeekGateway(_settings(), client=client).generate_structured(
                system_prompt="system",
                user_prompt="hello",
                response_model=ResponseDraft,
            )

    assert attempts == 1
    assert exc_info.value.error.code == "model_http_error"
    assert exc_info.value.error.retryable is False


@pytest.mark.asyncio
async def test_timeout_is_retried_then_returns_safe_error() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelGatewayError) as exc_info:
            await DeepSeekGateway(_settings(), client=client).generate_structured(
                system_prompt="system",
                user_prompt="hello",
                response_model=ResponseDraft,
            )

    assert attempts == 2
    assert exc_info.value.error.code == "model_timeout"
    assert exc_info.value.error.retryable is True


@pytest.mark.asyncio
async def test_invalid_json_returns_structured_error_without_response_echo() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelGatewayError) as exc_info:
            await DeepSeekGateway(_settings(), client=client).generate_structured(
                system_prompt="system",
                user_prompt="hello",
                response_model=ResponseDraft,
            )

    assert exc_info.value.error.code == "model_invalid_json"
    assert "not-json" not in exc_info.value.error.safe_message


@pytest.mark.asyncio
async def test_fake_gateway_is_offline_and_returns_structured_response() -> None:
    gateway = FakeModelGateway(
        ResponseDraft(answer="离线回复", next_action="finish", confidence=0.7)
    )

    result, usage = await gateway.generate_structured(
        system_prompt="system",
        user_prompt="hello",
        response_model=ResponseDraft,
    )

    assert result.answer == "离线回复"
    assert usage.provider == "fake"
    assert usage.latency_ms == 0
