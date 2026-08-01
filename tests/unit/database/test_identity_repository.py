from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.database.base import TenantScope


@pytest.fixture
def repository(session):
    from backend.database.repositories.identity import IdentityRepository

    return IdentityRepository(session)


@pytest.mark.asyncio
async def test_user_lookup_requires_tenant_id(repository, tenant_a, tenant_b, user):
    result = await repository.get_user_in_tenant(
        scope=TenantScope(tenant_id=tenant_b.id),
        user_id=user.id,
    )

    assert result is None


@pytest.mark.asyncio
async def test_user_lookup_ignores_soft_deleted_rows(repository, session, tenant_a, user):
    user.deleted_at = datetime.now(timezone.utc)
    await session.commit()

    result = await repository.get_user_in_tenant(
        scope=TenantScope(tenant_id=tenant_a.id),
        user_id=user.id,
    )

    assert result is None


@pytest.mark.asyncio
async def test_list_user_roles_returns_only_active_roles(repository, session, tenant_a, user):
    from backend.database.models.identity import Permission, Role, UserRole

    role = Role(
        id=uuid4(),
        tenant_id=tenant_a.id,
        code="support_agent",
        name="Support Agent",
        status="active",
        is_platform_role=False,
    )
    deleted_role = Role(
        id=uuid4(),
        tenant_id=tenant_a.id,
        code="deleted_role",
        name="Deleted Role",
        status="inactive",
        is_platform_role=False,
        deleted_at=datetime.now(timezone.utc),
    )
    session.add_all(
        [
            role,
            deleted_role,
            UserRole(id=uuid4(), tenant_id=tenant_a.id, user_id=user.id, role_id=role.id),
            UserRole(id=uuid4(), tenant_id=tenant_a.id, user_id=user.id, role_id=deleted_role.id),
        ]
    )
    await session.commit()

    roles = await repository.list_user_roles(
        scope=TenantScope(tenant_id=tenant_a.id),
        user_id=user.id,
    )

    assert [item.code for item in roles] == ["support_agent"]


@pytest.mark.asyncio
async def test_has_permission_requires_same_tenant(repository, session, tenant_a, tenant_b, user):
    from backend.database.models.identity import Permission, Role, UserRole

    role = Role(
        id=uuid4(),
        tenant_id=tenant_a.id,
        code="refund_operator",
        name="Refund Operator",
        status="active",
        is_platform_role=False,
    )
    permission = Permission(
        id=uuid4(),
        tenant_id=tenant_a.id,
        role_id=role.id,
        code="refund:approve",
        name="Approve refund",
        status="active",
    )
    session.add_all(
        [
            role,
            permission,
            UserRole(id=uuid4(), tenant_id=tenant_a.id, user_id=user.id, role_id=role.id),
        ]
    )
    await session.commit()

    assert await repository.has_permission(
        scope=TenantScope(tenant_id=tenant_b.id),
        user_id=user.id,
        permission_code="refund:approve",
    ) is False
