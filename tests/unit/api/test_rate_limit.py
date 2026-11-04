from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from backend.api.rate_limit import (
    InMemoryFixedWindowRateLimiter,
    get_rate_limit_max_clients,
    get_rate_limit_requests,
    get_rate_limit_window_seconds,
)
from backend.main import create_app


def test_rate_limit_returns_structured_429_with_retry_headers(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    client = TestClient(create_app())

    first = client.get("/does-not-exist")
    second = client.get("/does-not-exist")
    limited = client.get(
        "/does-not-exist",
        headers={"X-Request-Id": "rate-limit-test"},
    )

    assert first.status_code == 404
    assert first.headers["ratelimit-limit"] == "2"
    assert first.headers["ratelimit-remaining"] == "1"
    assert second.status_code == 404
    assert second.headers["ratelimit-remaining"] == "0"
    assert limited.status_code == 429
    assert limited.json() == {
        "error": {
            "code": "rate_limit_exceeded",
            "message": "request rate limit exceeded",
            "request_id": "rate-limit-test",
        }
    }
    assert limited.headers["ratelimit-limit"] == "2"
    assert limited.headers["ratelimit-remaining"] == "0"
    assert limited.headers["ratelimit-reset"] == limited.headers["retry-after"]
    assert limited.headers["x-request-id"] == "rate-limit-test"
    assert limited.headers["x-content-type-options"] == "nosniff"


def test_spoofed_forwarded_for_does_not_bypass_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    client = TestClient(create_app())

    first = client.get("/does-not-exist", headers={"X-Forwarded-For": "192.0.2.1"})
    limited = client.get(
        "/does-not-exist",
        headers={"X-Forwarded-For": "198.51.100.2"},
    )

    assert first.status_code == 404
    assert limited.status_code == 429


def test_health_and_preflight_requests_do_not_consume_limit(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    client = TestClient(create_app())

    for _ in range(3):
        assert client.get("/healthz").status_code == 200
        assert client.options("/does-not-exist").status_code in {200, 405}

    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.headers["ratelimit-remaining"] == "0"


@pytest.mark.asyncio
async def test_rate_limit_window_resets_without_retaining_expired_client() -> None:
    current_time = [10.0]
    limiter = InMemoryFixedWindowRateLimiter(
        requests=1,
        window_seconds=5,
        max_clients=1,
        clock=lambda: current_time[0],
    )

    assert (await limiter.check("client-a")).allowed
    assert not (await limiter.check("client-a")).allowed
    assert not (await limiter.check("client-b")).allowed

    current_time[0] = 15.0

    reset = await limiter.check("client-b")
    assert reset.allowed
    assert reset.remaining == 0
    assert reset.reset_after_seconds == 5


@pytest.mark.parametrize("value", ("0", "-1", "1.5", "not-an-integer"))
def test_rate_limit_rejects_invalid_request_count(value: str) -> None:
    with pytest.raises(ValueError, match="RATE_LIMIT_REQUESTS"):
        get_rate_limit_requests(value)


@pytest.mark.parametrize("value", ("0", "-1", "nan", "inf", "not-a-number"))
def test_rate_limit_rejects_invalid_window(value: str) -> None:
    with pytest.raises(ValueError, match="RATE_LIMIT_WINDOW_SECONDS"):
        get_rate_limit_window_seconds(value)


@pytest.mark.parametrize("value", ("0", "-1", "1.5", "not-an-integer"))
def test_rate_limit_rejects_invalid_client_capacity(value: str) -> None:
    with pytest.raises(ValueError, match="RATE_LIMIT_MAX_CLIENTS"):
        get_rate_limit_max_clients(value)
