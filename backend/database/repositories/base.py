from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.base import TenantScope


class BaseRepository:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
