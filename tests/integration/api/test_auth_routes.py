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
