from __future__ import annotations

import os
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


DEFAULT_MAX_REQUEST_BODY_BYTES = 1024 * 1024
BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


def get_max_request_body_bytes(raw: str | None = None) -> int:
    value = os.getenv(
        "MAX_REQUEST_BODY_BYTES", str(DEFAULT_MAX_REQUEST_BODY_BYTES)
    ) if raw is None else raw
    try:
        limit = int(value)
    except ValueError as exc:
        raise ValueError("MAX_REQUEST_BODY_BYTES must be an integer") from exc
    if limit <= 0:
        raise ValueError("MAX_REQUEST_BODY_BYTES must be greater than zero")
    return limit


def _error_response(request: Request, *, code: str, message: str, status_code: int) -> JSONResponse:
    request_id = (
        getattr(request.state, "request_id", None)
        or request.headers.get("X-Request-Id")
        or f"request-{uuid4().hex}"
    )
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
    )


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_body_bytes: int) -> None:
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method not in BODY_METHODS:
            return await call_next(request)

        content_length = request.headers.get("Content-Length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                return _error_response(
                    request,
                    code="invalid_content_length",
                    message="Content-Length must be an integer",
                    status_code=400,
                )
            if declared_length < 0:
                return _error_response(
                    request,
                    code="invalid_content_length",
                    message="Content-Length must not be negative",
                    status_code=400,
                )
            if declared_length > self.max_body_bytes:
                return self._too_large(request)

        chunks: list[bytes] = []
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > self.max_body_bytes:
                return self._too_large(request)
            chunks.append(chunk)
        request._body = b"".join(chunks)  # noqa: SLF001 - replay the bounded body downstream
        return await call_next(request)

    def _too_large(self, request: Request) -> JSONResponse:
        return _error_response(
            request,
            code="request_too_large",
            message=f"request body exceeds {self.max_body_bytes} bytes",
            status_code=413,
        )


def configure_request_body_limit(app: FastAPI) -> None:
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=get_max_request_body_bytes(),
    )


__all__ = [
    "BODY_METHODS",
    "DEFAULT_MAX_REQUEST_BODY_BYTES",
    "RequestBodyLimitMiddleware",
    "configure_request_body_limit",
    "get_max_request_body_bytes",
]
