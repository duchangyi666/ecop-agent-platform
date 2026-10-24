from __future__ import annotations

import asyncio
import math
import os
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
TIMEOUT_EXEMPT_PATHS = frozenset({"/api/v1/customer-consultations/stream"})
TIMEOUT_EXEMPT_PREFIXES = ("/mcp/",)


def get_request_timeout_seconds(raw: str | None = None) -> float:
    value = (
        os.getenv("REQUEST_TIMEOUT_SECONDS", str(DEFAULT_REQUEST_TIMEOUT_SECONDS))
        if raw is None
        else raw
    )
    try:
        timeout_seconds = float(value)
    except ValueError as exc:
        raise ValueError("REQUEST_TIMEOUT_SECONDS must be a number") from exc
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError(
            "REQUEST_TIMEOUT_SECONDS must be a finite number greater than zero"
        )
    return timeout_seconds


def is_timeout_exempt_path(path: str) -> bool:
    return path in TIMEOUT_EXEMPT_PATHS or path.startswith(TIMEOUT_EXEMPT_PREFIXES)


def _timeout_response(request: Request, timeout_seconds: float) -> JSONResponse:
    request_id = (
        getattr(request.state, "request_id", None)
        or request.headers.get("X-Request-Id")
        or f"request-{uuid4().hex}"
    )
    return JSONResponse(
        status_code=504,
        content={
            "error": {
                "code": "request_timeout",
                "message": (
                    f"request exceeded the {timeout_seconds:g} second processing deadline"
                ),
                "request_id": request_id,
            }
        },
    )


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, timeout_seconds: float) -> None:
        super().__init__(app)
        self.timeout_seconds = timeout_seconds

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if is_timeout_exempt_path(request.url.path):
            return await call_next(request)
        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout_seconds,
            )
        except TimeoutError:
            return _timeout_response(request, self.timeout_seconds)


def configure_request_timeout(app: FastAPI) -> None:
    app.add_middleware(
        RequestTimeoutMiddleware,
        timeout_seconds=get_request_timeout_seconds(),
    )


__all__ = [
    "DEFAULT_REQUEST_TIMEOUT_SECONDS",
    "RequestTimeoutMiddleware",
    "TIMEOUT_EXEMPT_PATHS",
    "TIMEOUT_EXEMPT_PREFIXES",
    "configure_request_timeout",
    "get_request_timeout_seconds",
    "is_timeout_exempt_path",
]
