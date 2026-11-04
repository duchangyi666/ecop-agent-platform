from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math
import os
import time
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


DEFAULT_RATE_LIMIT_REQUESTS = 120
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60.0
DEFAULT_RATE_LIMIT_MAX_CLIENTS = 10_000
RATE_LIMIT_EXEMPT_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})


def _positive_int(name: str, raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def get_rate_limit_requests(raw: str | None = None) -> int:
    value = (
        os.getenv("RATE_LIMIT_REQUESTS", str(DEFAULT_RATE_LIMIT_REQUESTS))
        if raw is None
        else raw
    )
    return _positive_int("RATE_LIMIT_REQUESTS", value)


def get_rate_limit_window_seconds(raw: str | None = None) -> float:
    value = (
        os.getenv(
            "RATE_LIMIT_WINDOW_SECONDS",
            str(DEFAULT_RATE_LIMIT_WINDOW_SECONDS),
        )
        if raw is None
        else raw
    )
    try:
        seconds = float(value)
    except ValueError as exc:
        raise ValueError("RATE_LIMIT_WINDOW_SECONDS must be a number") from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError(
            "RATE_LIMIT_WINDOW_SECONDS must be a finite number greater than zero"
        )
    return seconds


def get_rate_limit_max_clients(raw: str | None = None) -> int:
    value = (
        os.getenv("RATE_LIMIT_MAX_CLIENTS", str(DEFAULT_RATE_LIMIT_MAX_CLIENTS))
        if raw is None
        else raw
    )
    return _positive_int("RATE_LIMIT_MAX_CLIENTS", value)


@dataclass
class _ClientWindow:
    count: int
    reset_at: float


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    reset_after_seconds: int


class InMemoryFixedWindowRateLimiter:
    def __init__(
        self,
        *,
        requests: int,
        window_seconds: float,
        max_clients: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.requests = requests
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._clock = clock
        self._windows: dict[str, _ClientWindow] = {}
        self._lock = asyncio.Lock()

    async def check(self, client_key: str) -> RateLimitDecision:
        async with self._lock:
            now = self._clock()
            window = self._windows.get(client_key)
            if window is None or now >= window.reset_at:
                if window is None and len(self._windows) >= self.max_clients:
                    self._prune_expired(now)
                if window is None and len(self._windows) >= self.max_clients:
                    reset_after = min(
                        self._reset_after(item.reset_at, now)
                        for item in self._windows.values()
                    )
                    return RateLimitDecision(False, 0, reset_after)
                window = _ClientWindow(count=0, reset_at=now + self.window_seconds)
                self._windows[client_key] = window

            reset_after = self._reset_after(window.reset_at, now)
            if window.count >= self.requests:
                return RateLimitDecision(False, 0, reset_after)

            window.count += 1
            return RateLimitDecision(
                True,
                self.requests - window.count,
                reset_after,
            )

    def _prune_expired(self, now: float) -> None:
        expired = [
            client_key
            for client_key, window in self._windows.items()
            if now >= window.reset_at
        ]
        for client_key in expired:
            del self._windows[client_key]

    @staticmethod
    def _reset_after(reset_at: float, now: float) -> int:
        return max(1, math.ceil(reset_at - now))


def _client_key(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown-client"


def _headers(*, limit: int, decision: RateLimitDecision) -> dict[str, str]:
    return {
        "RateLimit-Limit": str(limit),
        "RateLimit-Remaining": str(decision.remaining),
        "RateLimit-Reset": str(decision.reset_after_seconds),
    }


def _rate_limited_response(
    request: Request,
    *,
    limit: int,
    decision: RateLimitDecision,
) -> JSONResponse:
    request_id = (
        getattr(request.state, "request_id", None)
        or request.headers.get("X-Request-Id")
        or f"request-{uuid4().hex}"
    )
    headers = _headers(limit=limit, decision=decision)
    headers["Retry-After"] = str(decision.reset_after_seconds)
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limit_exceeded",
                "message": "request rate limit exceeded",
                "request_id": request_id,
            }
        },
        headers=headers,
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        requests: int,
        window_seconds: float,
        max_clients: int,
    ) -> None:
        super().__init__(app)
        self.limiter = InMemoryFixedWindowRateLimiter(
            requests=requests,
            window_seconds=window_seconds,
            max_clients=max_clients,
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method == "OPTIONS" or request.url.path in RATE_LIMIT_EXEMPT_PATHS:
            return await call_next(request)

        decision = await self.limiter.check(_client_key(request))
        headers = _headers(limit=self.limiter.requests, decision=decision)
        if not decision.allowed:
            return _rate_limited_response(
                request,
                limit=self.limiter.requests,
                decision=decision,
            )

        response = await call_next(request)
        response.headers.update(headers)
        return response


def configure_rate_limit(app: FastAPI) -> None:
    app.add_middleware(
        RateLimitMiddleware,
        requests=get_rate_limit_requests(),
        window_seconds=get_rate_limit_window_seconds(),
        max_clients=get_rate_limit_max_clients(),
    )


__all__ = [
    "DEFAULT_RATE_LIMIT_MAX_CLIENTS",
    "DEFAULT_RATE_LIMIT_REQUESTS",
    "DEFAULT_RATE_LIMIT_WINDOW_SECONDS",
    "InMemoryFixedWindowRateLimiter",
    "RATE_LIMIT_EXEMPT_PATHS",
    "RateLimitDecision",
    "RateLimitMiddleware",
    "configure_rate_limit",
    "get_rate_limit_max_clients",
    "get_rate_limit_requests",
    "get_rate_limit_window_seconds",
]
