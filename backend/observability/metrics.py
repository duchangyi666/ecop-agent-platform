from __future__ import annotations

from collections import Counter
from typing import Any

_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def create_metrics_state() -> dict[str, Any]:
    return {
        "requests": Counter(),
        "duration_buckets": Counter(),
        "duration_sum": Counter(),
        "duration_count": Counter(),
    }


def record_http_request(
    state: dict[str, Any],
    *,
    method: str,
    path: str,
    status_code: int,
    latency_seconds: float,
) -> None:
    state["requests"][(method, path, status_code)] += 1
    key = (method, path, status_code)
    state["duration_sum"][key] += latency_seconds
    state["duration_count"][key] += 1
    for bucket in _DURATION_BUCKETS:
        if latency_seconds <= bucket:
            state["duration_buckets"][(method, path, status_code, bucket)] += 1
    state["duration_buckets"][(method, path, status_code, "+Inf")] += 1


def _labels(method: str, path: str, status_code: int, extra: str = "") -> str:
    labels = f'method="{method}",path="{path}",status="{status_code}"'
    return f"{labels},{extra}" if extra else labels


def render_prometheus_metrics(state: dict[str, Any]) -> str:
    lines = [
        "# HELP ecop_http_requests_total Total HTTP requests handled by the API.",
        "# TYPE ecop_http_requests_total counter",
    ]
    requests: Counter[tuple[str, str, int]] = state.get("requests", Counter())
    for (method, path, status_code), count in sorted(requests.items()):
        lines.append(
            f"ecop_http_requests_total{{{_labels(method, path, status_code)}}} {count}"
        )

    lines.extend(
        [
            "# HELP ecop_http_request_duration_seconds HTTP request latency.",
            "# TYPE ecop_http_request_duration_seconds histogram",
        ]
    )
    buckets: Counter[tuple[str, str, int, Any]] = state.get("duration_buckets", Counter())
    for (method, path, status_code, bucket), count in sorted(
        buckets.items(),
        key=lambda item: (
            item[0][0],
            item[0][1],
            item[0][2],
            str(item[0][3]),
        ),
    ):
        le = "+Inf" if bucket == "+Inf" else str(bucket)
        le_label = 'le="' + le + '"'
        lines.append(
            "ecop_http_request_duration_seconds_bucket"
            f"{{{_labels(method, path, status_code, le_label)}}} {count}"
        )
    sums: Counter[tuple[str, str, int]] = state.get("duration_sum", Counter())
    counts: Counter[tuple[str, str, int]] = state.get("duration_count", Counter())
    for key in sorted(counts):
        method, path, status_code = key
        labels = _labels(method, path, status_code)
        lines.append(f"ecop_http_request_duration_seconds_sum{{{labels}}} {sums[key]:.6f}")
        lines.append(f"ecop_http_request_duration_seconds_count{{{labels}}} {counts[key]}")

    lines.append("# HELP ecop_health_status Current application health status.")
    lines.append("# TYPE ecop_health_status gauge")
    lines.append("ecop_health_status 1")
    return "\n".join(lines) + "\n"


__all__ = [
    "create_metrics_state",
    "record_http_request",
    "render_prometheus_metrics",
]
