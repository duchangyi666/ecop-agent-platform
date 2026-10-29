from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from backend.api.dependencies import get_session_factory_dependency
from backend.auth.tokens import create_access_token
from backend.main import create_app


@pytest.mark.parametrize("mode", ("oidc", "jwt-only"))
@pytest.mark.parametrize("path", (
    "/api/v1/identity/tenants",
    "/api/v1/identity/tenants/00000000-0000-0000-0000-000000000001/users",
))
@pytest.mark.parametrize("credential", ("none", "invalid", "dev_headers", "valid_token"))
def test_identity_picker_is_unavailable_outside_dev_before_database_access(
    monkeypatch, mode: str, path: str, credential: str,
) -> None:
    monkeypatch.setenv("AUTH_MODE", mode)
    secret = "identity-test-secret-0123456789abcdef0123456789"
    monkeypatch.setenv("JWT_SECRET", secret)
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    user_id = UUID("00000000-0000-0000-0000-000000000002")
    headers: dict[str, str] = {}
    if credential == "invalid":
        headers["Authorization"] = "Bearer invalid"
    elif credential == "dev_headers":
        headers = {"X-Tenant-Id": str(tenant_id), "X-Actor-Id": str(user_id)}
    elif credential == "valid_token":
        token = create_access_token(
            tenant_id=tenant_id, user_id=user_id, actor_type="user", secret=secret,
        )
        headers["Authorization"] = f"Bearer {token}"
    app = create_app(knowledge_vector_store=None)

    def forbidden_database_access():
        raise AssertionError("disabled identity routes must not access the database")

    app.dependency_overrides[get_session_factory_dependency] = forbidden_database_access
    response = TestClient(app).get(path, headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert response.headers["x-request-id"]
