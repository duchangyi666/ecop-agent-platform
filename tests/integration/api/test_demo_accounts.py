from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import func, select

from backend.auth.permissions import ROLE_PERMISSIONS
from backend.database.models.identity import Permission, Role, User, UserRole
from scripts.seed_demo_accounts import DEMO_ACCOUNTS, seed_demo_accounts


@pytest.mark.asyncio
async def test_demo_accounts_are_repeatable_and_enforce_each_profile(
    database_url, session_factory, tenant_a, api_client, monkeypatch,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    first = await seed_demo_accounts(database_url=database_url, tenant_slug=tenant_a.slug)

    async def counts():
        async with session_factory() as session:
            return [
                await session.scalar(
                    select(func.count()).select_from(model).where(model.tenant_id == tenant_a.id)
                )
                for model in (User, Role, Permission, UserRole)
            ]

    before = await counts()
    second = await seed_demo_accounts(database_url=database_url, tenant_slug=tenant_a.slug)
    assert second == first
    assert await counts() == before
    assert len(first) == 5

    for identity in first:
        headers = {
            "X-Tenant-Id": identity["tenant_id"],
            "X-Actor-Id": identity["user_id"],
            "X-Actor-Type": "user",
        }
        me = api_client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200, me.text
        assert set(me.json()["permissions"]) == ROLE_PERMISSIONS[identity["profile"]]
        runtime = api_client.get("/api/v1/runtime/traces", headers=headers)
        expected = 200 if "runtime.read" in ROLE_PERMISSIONS[identity["profile"]] else 403
        assert runtime.status_code == expected, runtime.text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ("oidc", "jwt-only"))
async def test_demo_accounts_reject_non_development_modes(monkeypatch, mode) -> None:
    monkeypatch.setenv("AUTH_MODE", mode)
    with pytest.raises(ValueError, match="AUTH_MODE=dev"):
        await seed_demo_accounts(database_url="invalid-url")


@pytest.mark.asyncio
async def test_demo_accounts_do_not_reactivate_disabled_users(
    database_url, session_factory, tenant_a, tenant_a_user, monkeypatch,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    async with session_factory() as session:
        user = await session.get(User, tenant_a_user.id)
        user.email = DEMO_ACCOUNTS[-1].email
        user.status = "disabled"
        await session.commit()

    with pytest.raises(ValueError, match="inactive or deleted"):
        await seed_demo_accounts(database_url=database_url, tenant_slug=tenant_a.slug)

    async with session_factory() as session:
        user = await session.get(User, tenant_a_user.id)
        assert user.status == "disabled"
        # The earlier identities created in this attempt must roll back as well.
        assert await session.scalar(
            select(func.count()).select_from(User).where(User.tenant_id == tenant_a.id)
        ) == 1


@pytest.mark.asyncio
async def test_demo_accounts_refuse_to_hide_existing_extra_permissions(
    database_url, session_factory, tenant_a, monkeypatch,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    identities = await seed_demo_accounts(database_url=database_url, tenant_slug=tenant_a.slug)
    guest = next(item for item in identities if item["profile"] == "guest")
    async with session_factory() as session:
        role_id = await session.scalar(
            select(Permission.role_id).where(
                Permission.tenant_id == tenant_a.id, Permission.code == "refund.approve"
            )
        )
        session.add(UserRole(
            tenant_id=tenant_a.id, user_id=UUID(guest["user_id"]), role_id=role_id,
        ))
        await session.commit()

    with pytest.raises(ValueError, match="extra permissions"):
        await seed_demo_accounts(database_url=database_url, tenant_slug=tenant_a.slug)


@pytest.mark.asyncio
async def test_demo_accounts_preserve_existing_business_permission_ownership(
    database_url, session_factory, tenant_a, tenant_a_user, grant_permission, monkeypatch,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    await grant_permission(tenant_a_user.id, "knowledge.search")
    async with session_factory() as session:
        original_role = await session.scalar(
            select(Permission.role_id).where(Permission.tenant_id == tenant_a.id)
        )

    with pytest.raises(ValueError, match="non-demo or disabled permissions"):
        await seed_demo_accounts(database_url=database_url, tenant_slug=tenant_a.slug)

    async with session_factory() as session:
        assert await session.scalar(
            select(Permission.role_id).where(Permission.tenant_id == tenant_a.id)
        ) == original_role
        assert await session.scalar(
            select(func.count()).select_from(User).where(User.tenant_id == tenant_a.id)
        ) == 1
