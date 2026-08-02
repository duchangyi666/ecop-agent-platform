from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select

from backend.database.base import TenantScope
from backend.database.models.governance import Document, DocumentVersion
from backend.database.models.knowledge import KnowledgeChunk
from backend.database.repositories.base import TenantScopedRepository


class KnowledgeRepository(TenantScopedRepository):
    async def list_documents(
        self,
        *,
        scope: TenantScope,
        limit: int = 50,
        status: str | None = None,
    ) -> list[Document]:
        statement = select(Document).where(
            Document.tenant_id == scope.tenant_id,
            Document.deleted_at.is_(None),
        )
        if status:
            statement = statement.where(Document.status == status)
        statement = statement.order_by(Document.title).limit(limit)
        return list(await self.session.scalars(statement))

    async def get_document(
        self,
        *,
        scope: TenantScope,
        document_id: UUID,
    ) -> Document | None:
        statement = select(Document).where(
            Document.tenant_id == scope.tenant_id,
            Document.id == document_id,
            Document.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def archive_document(
        self,
        *,
        scope: TenantScope,
        document_id: UUID,
    ) -> Document | None:
        document = await self.get_document(scope=scope, document_id=document_id)
        if document is None:
            return None
        document.status = "archived"
        document.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
        return document

    async def list_document_chunks(
        self,
        *,
        scope: TenantScope,
        document_id: UUID,
    ) -> list[KnowledgeChunk]:
        statement = (
            self._tenant_visible(
                select(KnowledgeChunk),
                KnowledgeChunk,
                scope=scope,
            )
            .where(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.chunk_number)
        )
        return list(await self.session.scalars(statement))

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

    async def get_documents_by_ids(
        self,
        *,
        scope: TenantScope,
        document_ids: list[UUID],
    ) -> list[Document]:
        if not document_ids:
            return []
        statement = self._tenant_visible(select(Document), Document, scope=scope).where(
            Document.id.in_(document_ids),
            Document.status == "active",
        )
        return list(await self.session.scalars(statement))

    async def upsert_document(
        self,
        *,
        scope: TenantScope,
        external_document_id: str,
        title: str,
        source_uri: str | None,
        visibility: str,
    ) -> Document:
        statement = self._tenant_visible(select(Document), Document, scope=scope).where(
            Document.external_document_id == external_document_id,
        )
        document = await self.session.scalar(statement)
        if document is None:
            document = Document(
                id=uuid4(),
                tenant_id=scope.tenant_id,
                external_document_id=external_document_id,
                title=title,
                status="active",
                source_uri=source_uri,
                visibility=visibility,
            )
            self.session.add(document)
        else:
            document.title = title
            document.source_uri = source_uri
            document.visibility = visibility
            document.status = "active"
        await self.session.flush()
        return document

    async def next_document_version_number(
        self,
        *,
        scope: TenantScope,
        document_id: UUID,
    ) -> int:
        statement = (
            select(func.max(DocumentVersion.version_number))
            .where(
                DocumentVersion.tenant_id == scope.tenant_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.deleted_at.is_(None),
            )
        )
        current = await self.session.scalar(statement)
        return int(current or 0) + 1

    async def replace_document_chunks(
        self,
        *,
        scope: TenantScope,
        document_id: UUID,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        old_statement = self._tenant_visible(
            select(KnowledgeChunk),
            KnowledgeChunk,
            scope=scope,
        ).where(KnowledgeChunk.document_id == document_id)
        old_chunks = list(await self.session.scalars(old_statement))
        for chunk in old_chunks:
            await self.session.delete(chunk)
        for chunk in chunks:
            self.session.add(chunk)
        await self.session.flush()
        return chunks


__all__ = ["KnowledgeRepository"]
