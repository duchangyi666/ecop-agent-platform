"""Three-layer resilience: auto-retry -> agent degrade -> system fallback.

Mirrors the reference framework's ``with_retry`` so any LLM/tool/graph call can
be wrapped once and always degrades gracefully instead of raising to the client.
"""

from __future__ import annotations

import asyncio
import inspect
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

import httpx

from backend.llm.errors import ModelGatewayError

MAX_RETRIES = 2
RETRY_DELAYS = (1.0, 3.0)
TIMEOUT_PER_ATTEMPT = 120.0

T = TypeVar("T")


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, ModelGatewayError):
        return bool(exc.error.retryable)
    return isinstance(exc, (TimeoutError, ConnectionError, httpx.TransportError))


def with_retry(
    agent_type: str = "",
    agent_fallback: Callable[[BaseException], Any] | None = None,
    system_fallback: Callable[[BaseException], Any] | None = None,
):
    """Decorator: layer1 retry(1s/3s,<=2) -> layer2 agent degrade -> layer3 system."""

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last: BaseException | None = None
            for attempt in range(MAX_RETRIES + 1):
                try:
                    return await asyncio.wait_for(
                        fn(*args, **kwargs), timeout=TIMEOUT_PER_ATTEMPT
                    )
                except Exception as exc:  # noqa: BLE001 - classify below
                    last = exc
                    if not is_retryable(exc):
                        break
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
            # Layer 2: agent-level degraded response.
            if agent_fallback is not None:
                try:
                    result = agent_fallback(last)  # type: ignore[arg-type]
                    if inspect.isawaitable(result):
                        result = await result
                    return result
                except Exception:  # noqa: BLE001 - fall through to layer 3
                    pass
            # Layer 3: system fallback (must never fail).
            if system_fallback is not None:
                result = system_fallback(last)  # type: ignore[arg-type]
                if inspect.isawaitable(result):
                    result = await result
                return result
            raise last  # type: ignore[misc]

        return wrapper

    return decorator


__all__ = [
    "MAX_RETRIES",
    "RETRY_DELAYS",
    "TIMEOUT_PER_ATTEMPT",
    "is_retryable",
    "with_retry",
]
