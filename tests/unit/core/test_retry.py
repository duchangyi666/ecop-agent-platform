from __future__ import annotations

import pytest

from backend.core.retry import is_retryable, with_retry
from backend.llm.contracts import ModelCallError
from backend.llm.errors import ModelGatewayError


def _retryable_error() -> ModelGatewayError:
    return ModelGatewayError(
        ModelCallError(code="model_timeout", retryable=True, safe_message="timeout")
    )


@pytest.mark.asyncio
async def test_with_retry_returns_on_success() -> None:
    calls = {"n": 0}

    @with_retry()
    async def ok() -> str:
        calls["n"] += 1
        return "done"

    assert await ok() == "done"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_with_retry_retries_then_succeeds() -> None:
    calls = {"n": 0}

    @with_retry()
    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _retryable_error()
        return "recovered"

    assert await flaky() == "recovered"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_with_retry_agent_fallback_after_exhaustion() -> None:
    @with_retry(
        agent_type="qa",
        agent_fallback=lambda exc: {"fallback_used": True, "content": "degraded"},
    )
    async def always_fail() -> dict:
        raise _retryable_error()

    result = await always_fail()
    assert result["fallback_used"] is True
    assert result["content"] == "degraded"


@pytest.mark.asyncio
async def test_with_retry_system_fallback_when_agent_fallback_fails() -> None:
    @with_retry(
        agent_type="qa",
        agent_fallback=lambda exc: (_ for _ in ()).throw(ValueError("bad fallback")),
        system_fallback=lambda exc: {"fallback_used": True, "system": True},
    )
    async def always_fail() -> dict:
        raise _retryable_error()

    result = await always_fail()
    assert result["system"] is True


@pytest.mark.asyncio
async def test_non_retryable_raises_immediately() -> None:
    calls = {"n": 0}

    @with_retry()
    async def fatal() -> str:
        calls["n"] += 1
        raise ModelGatewayError(
            ModelCallError(code="model_invalid_output", retryable=False, safe_message="x")
        )

    with pytest.raises(ModelGatewayError):
        await fatal()
    assert calls["n"] == 1


def test_is_retryable_classification() -> None:
    assert is_retryable(_retryable_error()) is True
    assert is_retryable(TimeoutError()) is True
    assert is_retryable(ConnectionError()) is True
    fatal = ModelGatewayError(
        ModelCallError(code="model_invalid_output", retryable=False, safe_message="x")
    )
    assert is_retryable(fatal) is False
    assert is_retryable(ValueError("nope")) is False
