from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from backend.api.security_headers import CONTENT_SECURITY_POLICY, HSTS_HEADER
from backend.main import create_app
from backend.llm.contracts import ResponseDraft
from backend.llm.fake import FakeModelGateway


def test_health_check_returns_only_liveness_status() -> None:
    response = TestClient(create_app()).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_app_defaults_to_fake_model_gateway(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    app = create_app()

    assert isinstance(app.state.model_gateway, FakeModelGateway)


def test_create_app_accepts_explicit_model_gateway() -> None:
    gateway = FakeModelGateway(
        ResponseDraft(
            answer="测试回复",
            next_action="finish",
            confidence=0.9,
        )
    )

    app = create_app(model_gateway=gateway)

    assert app.state.model_gateway is gateway


def test_metrics_endpoint_exposes_prometheus_text() -> None:
    response = TestClient(create_app()).get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "ecop_health_status 1" in response.text


def test_application_adds_browser_security_headers() -> None:
    response = TestClient(create_app()).get("/healthz")

    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["permissions-policy"] == "camera=(), geolocation=(), microphone=()"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in response.headers


def test_application_adds_hsts_only_for_https_requests() -> None:
    client = TestClient(create_app(), base_url="https://testserver")

    response = client.get("/healthz")

    assert response.headers["strict-transport-security"] == HSTS_HEADER


def test_security_headers_are_present_on_error_responses() -> None:
    response = TestClient(create_app()).get("/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["x-content-type-options"] == "nosniff"


def test_cors_allows_only_an_explicit_origin(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://console.example.com")
    client = TestClient(create_app())

    allowed = client.options(
        "/healthz",
        headers={
            "Origin": "https://console.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,X-Request-Id",
        },
    )
    denied = client.get(
        "/healthz",
        headers={"Origin": "https://attacker.example"},
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://console.example.com"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert allowed.headers["access-control-max-age"] == "600"
    assert allowed.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert "access-control-allow-origin" not in denied.headers


def test_cors_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    response = TestClient(create_app()).get(
        "/healthz",
        headers={"Origin": "https://console.example.com"},
    )

    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "origins",
    (
        "*",
        "https://console.example.com/path",
        "https://user:password@console.example.com",
    ),
)
def test_cors_rejects_unsafe_or_invalid_origins(monkeypatch, origins: str) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", origins)

    with pytest.raises(ValueError, match="CORS"):
        create_app()


def test_request_body_limit_rejects_declared_oversized_payload(monkeypatch) -> None:
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "32")

    response = TestClient(create_app()).post(
        "/api/v1/auth/tokens",
        content=b"x" * 33,
        headers={"Content-Type": "application/json", "X-Request-Id": "limit-test"},
    )

    assert response.status_code == 413
    assert response.json() == {
        "error": {
            "code": "request_too_large",
            "message": "request body exceeds 32 bytes",
            "request_id": "limit-test",
        }
    }
    assert response.headers["x-request-id"] == "limit-test"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_request_body_limit_counts_streamed_chunks(monkeypatch) -> None:
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "32")

    response = TestClient(create_app()).post(
        "/api/v1/auth/tokens",
        content=iter((b"x" * 20, b"y" * 20)),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_request_body_at_limit_reaches_route_validation(monkeypatch) -> None:
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "32")

    response = TestClient(create_app()).post(
        "/api/v1/auth/tokens",
        content=b"{}",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("value", ("0", "-1", "not-an-integer"))
def test_request_body_limit_rejects_invalid_configuration(monkeypatch, value: str) -> None:
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", value)

    with pytest.raises(ValueError, match="MAX_REQUEST_BODY_BYTES"):
        create_app()
