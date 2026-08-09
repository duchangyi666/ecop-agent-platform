from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.llm.contracts import ResponseDraft
from backend.llm.fake import FakeModelGateway


def test_health_check_returns_ok_when_database_healthy(monkeypatch) -> None:
    async def _healthy() -> None:
        return None

    monkeypatch.setattr("backend.main.check_database_health", _healthy)

    response = TestClient(create_app()).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_check_reports_database_failure(monkeypatch) -> None:
    async def _unhealthy() -> None:
        raise RuntimeError("database is down")

    monkeypatch.setattr("backend.main.check_database_health", _unhealthy)

    response = TestClient(create_app()).get("/healthz")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"


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
