from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.api.schemas import ErrorResponse, HealthResponse
from backend.api.routes.refunds import router as refunds_router
from backend.domain.common import DomainError

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id") or f"request-{uuid4().hex}"


def _error_response(*, request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    payload = ErrorResponse(
        error={"code": code, "message": message, "request_id": _request_id(request)}
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def create_app() -> FastAPI:
    app = FastAPI(title="Enterprise Customer Operations Platform", version="0.1.0")

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok")

    app.include_router(refunds_router)

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return _error_response(
            request=request,
            status_code=exc.status_code,
            code=str(detail.get("code", "http_error")),
            message=str(detail.get("message", exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        del exc
        return _error_response(
            request=request,
            status_code=400,
            code="invalid_request",
            message="request validation failed",
        )

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        message = str(exc)
        code = "approval_not_pending" if "approval request is not pending" in message else "business_rule_rejected"
        status_code = 409 if code == "approval_not_pending" else 422
        return _error_response(request=request, status_code=status_code, code=code, message=message)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled api error", exc_info=exc)
        return _error_response(
            request=request,
            status_code=500,
            code="internal_error",
            message="internal server error",
        )

    return app


app = create_app()


__all__ = ["app", "create_app"]
