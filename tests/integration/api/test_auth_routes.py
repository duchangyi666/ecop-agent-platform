from __future__ import annotations

import pytest

from backend.auth.tokens import create_access_token


@pytest.mark.asyncio
async def test_local_token_route_issues_bearer_token_and_api_accepts_it(
    knowledge_api_client,
    tenant_a,
    tenant_a_user,
    monkeypatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")

    token_response = knowledge_api_client.post(
        "/api/v1/auth/tokens",
        json={
            "tenant_id": str(tenant_a.id),
            "user_id": str(tenant_a_user.id),
            "actor_type": "user",
        },
    )

    assert token_response.status_code == 200, token_response.text
    token = token_response.json()["access_token"]

    search_response = knowledge_api_client.get(
        "/api/v1/knowledge/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": "退款"},
    )

    assert search_response.status_code == 200, search_response.text


@pytest.mark.asyncio
async def test_api_rejects_invalid_bearer_token(
    knowledge_api_client,
    tenant_a,
    tenant_a_user,
    monkeypatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")

    response = knowledge_api_client.get(
        "/api/v1/knowledge/search",
        headers={"Authorization": "Bearer invalid-token"},
        params={"q": "退款"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


@pytest.mark.asyncio
async def test_api_rejects_expired_bearer_token(
    knowledge_api_client,
    tenant_a,
    tenant_a_user,
    monkeypatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")
    expired = create_access_token(
        tenant_id=tenant_a.id,
        user_id=tenant_a_user.id,
        actor_type="user",
        secret="test-secret-0123456789abcdef0123456789abcdef",
        expires_minutes=-1,
    )

    response = knowledge_api_client.get(
        "/api/v1/knowledge/search",
        headers={"Authorization": f"Bearer {expired}"},
        params={"q": "退款"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_returns_roles_and_permissions(
    knowledge_api_client,
    api_headers,
    tenant_a,
    tenant_a_user,
) -> None:
    response = knowledge_api_client.get("/api/v1/auth/me", headers=api_headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["tenant_id"] == str(tenant_a.id)
    assert payload["user_id"] == str(tenant_a_user.id)
    assert "knowledge.search" in payload["permissions"]
    assert payload["roles"]


@pytest.mark.asyncio
async def test_oidc_mode_disables_dev_headers_and_local_token_issuance(
    knowledge_api_client,
    tenant_a,
    tenant_a_user,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")

    mode_response = knowledge_api_client.get("/api/v1/auth/mode")
    assert mode_response.status_code == 200
    assert mode_response.json()["mode"] == "oidc"

    token_response = knowledge_api_client.post(
        "/api/v1/auth/tokens",
        json={
            "tenant_id": str(tenant_a.id),
            "user_id": str(tenant_a_user.id),
            "actor_type": "user",
        },
    )
    assert token_response.status_code == 403
    assert token_response.json()["error"]["code"] == "local_token_issuance_disabled"

    header_response = knowledge_api_client.get(
        "/api/v1/knowledge/search",
        headers={
            "X-Tenant-Id": str(tenant_a.id),
            "X-Actor-Id": str(tenant_a_user.id),
            "X-Actor-Type": "user",
        },
        params={"q": "退款"},
    )
    assert header_response.status_code == 401
    assert header_response.json()["error"]["code"] == "authentication_required"

    token = create_access_token(
        tenant_id=tenant_a.id,
        user_id=tenant_a_user.id,
        actor_type="user",
        secret="test-secret-0123456789abcdef0123456789abcdef",
    )
    bearer_response = knowledge_api_client.get(
        "/api/v1/knowledge/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": "退款"},
    )
    assert bearer_response.status_code == 200, bearer_response.text
