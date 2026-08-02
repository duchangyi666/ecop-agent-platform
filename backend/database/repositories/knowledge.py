from __future__ import annotations

from sqlalchemy import or_, select

from backend.database.base import TenantScope
from backend.database.models.governance import Document
from backend.database.repositories.base import TenantScopedRepository


class KnowledgeRepository(TenantScopedRepository):
    async def search_documents(
        self,
        *,
        scope: TenantScope,
        query: str,
        limit: int = 10,
    ) -> list[Document]:
        normalized = query.strip()
        if not normalized:
            return []
        pattern = f"%{normalized}%"
        statement = (
            self._tenant_visible(select(Document), Document, scope=scope)
            .where(
                Document.status == "active",
                or_(
                    Document.title.ilike(pattern),
                    Document.external_document_id.ilike(pattern),
                    Document.source_uri.ilike(pattern),
                ),
            )
            .order_by(Document.title)
            .limit(limit)
        )
        return list(await self.session.scalars(statement))


__all__ = ["KnowledgeRepository"]
