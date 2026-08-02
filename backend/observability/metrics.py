from __future__ import annotations

from collections import Counter
from typing import Any


def render_prometheus_metrics(state: dict[str, Any]) -> str:
    lines = [
        "# HELP ecop_http_requests_total Total HTTP requests handled by the API.",
        "# TYPE ecop_http_requests_total counter",
    ]
    requests: Counter[tuple[str, str, int]] = state.get("requests", Counter())
    for (method, path, status_code), count in sorted(requests.items()):
        labels = (
            f'method="{method}",path="{path}",status="{status_code}"'
        )
        lines.append(f"ecop_http_requests_total{{{labels}}} {count}")
    lines.append("# HELP ecop_health_status Current application health status.")
    lines.append("# TYPE ecop_health_status gauge")
    lines.append("ecop_health_status 1")
    return "\n".join(lines) + "\n"


def create_metrics_state() -> dict[str, Counter[tuple[str, str, int]]]:
    return {"requests": Counter()}


__all__ = ["create_metrics_state", "render_prometheus_metrics"]
