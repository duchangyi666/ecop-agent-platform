"""Structured request logging with correlation IDs.

`LOG_FORMAT=json` is intended for staging/production log pipelines;
`text` keeps local runs readable. Neither format ever receives Prompt or
credential values because call sites only pass bounded metadata.
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextvars import ContextVar, Token
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("ecop_request_id", default=None)
_configured = False


def set_request_id(value: str) -> Token[str | None]:
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def current_request_id() -> str | None:
    return _request_id.get()


def _trace_id() -> str | None:
    try:
        from opentelemetry import trace

        context = trace.get_current_span().get_span_context()
        if context.is_valid:
            return format(context.trace_id, "032x")
    except Exception:  # noqa: BLE001 - tracing is optional
        return None
    return None


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or current_request_id()
        if request_id:
            payload["request_id"] = request_id
        trace_id = getattr(record, "trace_id", None) or _trace_id()
        if trace_id:
            payload["trace_id"] = trace_id
        for key in ("method", "path", "status_code", "latency_ms", "tenant_id", "event"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "text").strip().lower()
    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s "
                "request_id=%(request_id)s method=%(method)s path=%(path)s "
                "status=%(status_code)s latency_ms=%(latency_ms)s %(message)s",
                defaults={
                    "request_id": "-",
                    "method": "-",
                    "path": "-",
                    "status_code": "-",
                    "latency_ms": "-",
                },
            )
        )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    logging.getLogger("pymilvus").setLevel(logging.WARNING)
    _configured = True


__all__ = [
    "JsonFormatter",
    "configure_logging",
    "current_request_id",
    "reset_request_id",
    "set_request_id",
]
