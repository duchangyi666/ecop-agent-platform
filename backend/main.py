from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
import logging
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.api.cors import configure_cors
from backend.api.request_limits import configure_request_body_limit
from backend.api.schemas import ErrorResponse, HealthResponse
from backend.api.security_headers import apply_security_headers
from backend.api.routes.auth import router as auth_router
from backend.api.routes.approvals import router as approvals_router
from backend.api.routes.conversations import router as conversations_router
from backend.api.routes.customer_service import router as customer_service_router
from backend.api.routes.evaluations import router as evaluations_router
from backend.api.routes.identity import router as identity_router
from backend.api.routes.knowledge import router as knowledge_router
from backend.api.routes.refunds import router as refunds_router
from backend.api.routes.runtime import router as runtime_router
from backend.api.routes.tickets import router as tickets_router
from backend.domain.common import DomainError
from backend.llm.factory import create_model_gateway
from backend.llm.gateway import ModelGateway
from backend.observability.logging import (
    configure_logging,
    reset_request_id,
    set_request_id,
)
from backend.observability.metrics import (
    create_metrics_state,
    record_http_request,
    render_prometheus_metrics,
)
from backend.observability.readiness import readiness_report
from backend.observability.tracing import setup_tracing
from backend.rag.vector_store import KnowledgeVectorStore, create_knowledge_vector_store

logger = logging.getLogger(__name__)
_UNSET = object()
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend_legacy"


def _request_id(request: Request) -> str:
    return (
        getattr(request.state, "request_id", None)
        or request.headers.get("X-Request-Id")
        or f"request-{uuid4().hex}"
    )


def _error_response(*, request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    payload = ErrorResponse(
        error={"code": code, "message": message, "request_id": _request_id(request)}
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Enter each mounted MCP sub-app's lifespan so its streamable-HTTP task
    # group is initialised (FastMCP requires run()/lifespan before serving).
    stack = AsyncExitStack()
    for sub_app in getattr(app.state, "mcp_apps", []) or []:
        await stack.enter_async_context(sub_app.router.lifespan_context(sub_app))
    try:
        yield
    finally:
        await stack.aclose()
        gateway = getattr(app.state, "model_gateway", None)
        close = getattr(gateway, "aclose", None)
        if close is not None:
            await close()
        vector_store = getattr(app.state, "knowledge_vector_store", None)
        close_vector_store = getattr(vector_store, "close", None)
        if close_vector_store is not None:
            await close_vector_store()


def create_app(
    model_gateway: ModelGateway | None = None,
    knowledge_vector_store: KnowledgeVectorStore | None | Any = _UNSET,
) -> FastAPI:
    configure_logging()
    app = FastAPI(title="Enterprise Customer Operations Platform", version="0.1.0", lifespan=lifespan)
    app.state.model_gateway = model_gateway or create_model_gateway()
    app.state.metrics = create_metrics_state()
    if knowledge_vector_store is _UNSET:
        knowledge_vector_store = create_knowledge_vector_store()
    app.state.knowledge_vector_store = knowledge_vector_store
    setup_tracing(app)
    configure_cors(app)
    configure_request_body_limit(app)

    @app.middleware("http")
    async def observe_http_requests(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or f"request-{uuid4().hex}"
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "http_request_failed",
                extra={"request_id": request_id, "method": request.method, "path": request.url.path},
            )
            raise
        finally:
            reset_request_id(token)
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_http_request(
            app.state.metrics,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_seconds=latency_ms / 1000,
        )
        response.headers["X-Request-Id"] = request_id
        apply_security_headers(response, is_https=request.url.scheme == "https")
        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
            },
        )
        return response

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        ready, components = await readiness_report()
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ready" if ready else "not_ready", "components": components},
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(
            content=render_prometheus_metrics(app.state.metrics),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    app.include_router(refunds_router)
    app.include_router(approvals_router)
    app.include_router(conversations_router)
    app.include_router(customer_service_router)
    app.include_router(tickets_router)
    app.include_router(knowledge_router)
    app.include_router(auth_router)
    app.include_router(evaluations_router)
    app.include_router(identity_router)
    app.include_router(runtime_router)

    # Mount in-process MCP servers (knowledge + web search) before the static
    # catch-all so /mcp/* is reachable. Guarded so a missing `mcp` dependency or
    # import issue never blocks startup.
    try:
        from backend.mcp.knowledge_base_server import mcp as kb_mcp
        from backend.mcp.web_search_server import mcp as ws_mcp

        kb_app = kb_mcp.streamable_http_app()
        ws_app = ws_mcp.streamable_http_app()
        app.mount("/mcp/kb", kb_app)
        app.mount("/mcp/web-search", ws_app)
        app.state.mcp_apps = [kb_app, ws_app]
    except Exception as exc:  # noqa: BLE001 - MCP is optional
        app.state.mcp_apps = []
        logger.warning("mcp mount skipped: %s", exc)

    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

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
