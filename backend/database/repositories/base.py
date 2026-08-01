from __future__ import annotations

from typing import Any

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.base import TenantScope


class BaseRepository:
    def __init__(self, session: AsyncSession, scope: TenantScope | None = None) -> None:
        self.session = session
        self.scope = scope


class TenantScopedRepository(BaseRepository):
    """Shared query builder that makes tenant and soft-delete predicates explicit."""

    @staticmethod
    def _tenant_visible(statement: Select[Any], model: type[Any], *, scope: TenantScope) -> Select[Any]:
        return statement.where(model.tenant_id == scope.tenant_id, model.deleted_at.is_(None))


__all__ = ["BaseRepository", "TenantScopedRepository"]
