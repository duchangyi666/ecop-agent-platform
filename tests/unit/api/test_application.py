from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import create_app


def test_health_check_returns_only_liveness_status() -> None:
    response = TestClient(create_app()).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
