from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_development_identity_picker_lists_tenant_and_user(
    api_client, tenant_a, tenant_a_user, monkeypatch,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")

    tenants = api_client.get("/api/v1/identity/tenants")
    assert tenants.status_code == 200, tenants.text
    assert any(item["id"] == str(tenant_a.id) for item in tenants.json()["tenants"])

    users = api_client.get(f"/api/v1/identity/tenants/{tenant_a.id}/users")
    assert users.status_code == 200, users.text
    assert any(item["id"] == str(tenant_a_user.id) for item in users.json()["users"])
