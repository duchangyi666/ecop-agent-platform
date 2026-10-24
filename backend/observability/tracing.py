"""Optional OpenTelemetry wiring.

Disabled by default (`OTEL_ENABLED=0`) so tests and offline demos do not try to
reach a collector. Enable it in staging with an OTLP endpoint; set
`OTEL_CONSOLE_EXPORTER=1` only for a short local debugging session.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.getenv("OTEL_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


def setup_tracing(app) -> None:
    if not _enabled():
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except ImportError as exc:  # pragma: no cover - optional dependency guard
        logger.warning("opentelemetry is not installed; tracing disabled: %s", exc)
        return

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", "clouddesk-api"),
            "service.version": os.getenv("OTEL_SERVICE_VERSION", "0.1.0"),
            "deployment.environment": os.getenv("DEPLOYMENT_ENV", "local"),
        }
    )
    provider = TracerProvider(resource=resource)
    if endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces"))
        )
    elif os.getenv("OTEL_CONSOLE_EXPORTER", "0").strip().lower() in {"1", "true", "yes", "on"}:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="/healthz,/readyz,/metrics",
    )
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    try:
        from backend.database.session import get_async_engine

        SQLAlchemyInstrumentor().instrument(
            tracer_provider=provider,
            engine=get_async_engine().sync_engine,
        )
    except Exception as exc:  # noqa: BLE001 - tracing must never block startup
        logger.warning("sqlalchemy tracing skipped: %s", exc)
    logger.info("opentelemetry tracing enabled endpoint=%s", endpoint or "none")


__all__ = ["setup_tracing"]
