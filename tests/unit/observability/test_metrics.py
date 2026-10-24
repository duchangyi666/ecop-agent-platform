from __future__ import annotations

from backend.observability.metrics import (
    create_metrics_state,
    record_http_request,
    render_prometheus_metrics,
)


def test_http_metrics_render_counter_and_histogram() -> None:
    state = create_metrics_state()
    record_http_request(
        state,
        method="GET",
        path="/healthz",
        status_code=200,
        latency_seconds=0.012,
    )

    text = render_prometheus_metrics(state)

    assert (
        'ecop_http_requests_total{method="GET",path="/healthz",status="200"} 1'
        in text
    )
    assert (
        'ecop_http_request_duration_seconds_bucket{method="GET",path="/healthz",'
        'status="200",le="0.025"} 1'
        in text
    )
    assert (
        'ecop_http_request_duration_seconds_count{method="GET",path="/healthz",'
        'status="200"} 1'
        in text
    )
    assert "ecop_health_status 1" in text
