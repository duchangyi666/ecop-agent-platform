from __future__ import annotations

import json
import logging

from backend.observability.logging import (
    JsonFormatter,
    reset_request_id,
    set_request_id,
)


def _record(message: str) -> logging.LogRecord:
    record = logging.LogRecord(
        name="backend.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.method = "GET"
    record.path = "/healthz"
    record.status_code = 200
    record.latency_ms = 12
    return record


def test_json_logger_includes_correlation_fields() -> None:
    token = set_request_id("req-test-1")
    try:
        payload = json.loads(JsonFormatter().format(_record("http_request")))
    finally:
        reset_request_id(token)

    assert payload["level"] == "INFO"
    assert payload["request_id"] == "req-test-1"
    assert payload["method"] == "GET"
    assert payload["path"] == "/healthz"
    assert payload["status_code"] == 200
    assert payload["latency_ms"] == 12


def test_json_logger_does_not_require_request_context() -> None:
    payload = json.loads(JsonFormatter().format(_record("startup")))

    assert payload["message"] == "startup"
    assert "request_id" not in payload
