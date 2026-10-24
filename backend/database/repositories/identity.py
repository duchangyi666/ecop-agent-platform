from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.base import TenantScope
from backend.database.models.billing import CustomerContact
from backend.database.models.identity import Permission, Role, User, UserRole
from backend.database.repositories.base import TenantScopedRepository


class IdentityRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_user_in_tenant(self, *, scope: TenantScope, user_id: UUID) -> User | None:
        statement = self._tenant_visible(select(User), User, scope=scope).where(User.id == user_id)
        return await self.session.scalar(statement)

    async def list_user_roles(self, *, scope: TenantScope, user_id: UUID) -> list[Role]:
        statement = (
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .join(User, User.id == UserRole.user_id)
            .where(UserRole.user_id == user_id)
        )
        statement = self._tenant_visible(statement, Role, scope=scope)
        statement = statement.where(
            UserRole.tenant_id == scope.tenant_id,
            UserRole.deleted_at.is_(None),
            User.tenant_id == scope.tenant_id,
            User.deleted_at.is_(None),
        )
        result = await self.session.scalars(statement.order_by(Role.code))
        return list(result.all())

    async def has_permission(self, *, scope: TenantScope, user_id: UUID, permission_code: str) -> bool:
        statement = (
            select(Permission.id)
            .join(Role, Role.id == Permission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .join(User, User.id == UserRole.user_id)
            .where(
                UserRole.user_id == user_id,
                UserRole.tenant_id == scope.tenant_id,
                UserRole.deleted_at.is_(None),
                User.tenant_id == scope.tenant_id,
                User.deleted_at.is_(None),
                Role.tenant_id == scope.tenant_id,
                Role.deleted_at.is_(None),
                Role.status == "active",
                Permission.tenant_id == scope.tenant_id,
                Permission.deleted_at.is_(None),
                Permission.status == "active",
                Permission.code == permission_code,
            )
            .limit(1)
        )
        return await self.session.scalar(statement) is not None

    async def list_user_permissions(
        self, *, scope: TenantScope, user_id: UUID
    ) -> list[str]:
        statement = (
            select(Permission.code)
            .join(Role, Role.id == Permission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .join(User, User.id == UserRole.user_id)
            .where(
                UserRole.user_id == user_id,
                UserRole.tenant_id == scope.tenant_id,
                UserRole.deleted_at.is_(None),
                User.tenant_id == scope.tenant_id,
                User.deleted_at.is_(None),
                Role.tenant_id == scope.tenant_id,
                Role.deleted_at.is_(None),
                Role.status == "active",
                Permission.tenant_id == scope.tenant_id,
                Permission.deleted_at.is_(None),
                Permission.status == "active",
            )
            .distinct()
            .order_by(Permission.code)
        )
        return list(await self.session.scalars(statement))

    async def get_customer_for_user(self, *, scope: TenantScope, user_id: UUID) -> UUID | None:
        statement = (
            select(CustomerContact.customer_id)
            .where(
                CustomerContact.user_id == user_id,
                CustomerContact.tenant_id == scope.tenant_id,
                CustomerContact.deleted_at.is_(None),
            )
            .limit(1)
        )
        return await self.session.scalar(statement)
