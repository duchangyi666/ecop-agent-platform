from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.state import KnowledgeEvidence
from backend.database.base import TenantScope
from backend.database.repositories.knowledge import KnowledgeRepository
from backend.rag.hybrid import merge_evidence
from backend.rag.vector_store import KnowledgeVectorStore


class ConsultationKnowledgeRetriever:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None,
        vector_store: KnowledgeVectorStore | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.vector_store = vector_store

    async def retrieve(
        self,
        *,
        scope: TenantScope,
        query: str,
        limit: int = 5,
    ) -> list[KnowledgeEvidence]:
        normalized = query.strip()
        if self.session_factory is None or not normalized:
            return []
        if self.vector_store is not None:
            return await self._retrieve_from_vector(scope=scope, query=normalized, limit=limit)
        return await self._retrieve_from_postgres(scope=scope, query=normalized, limit=limit)

    async def _retrieve_from_vector(
        self,
        *,
        scope: TenantScope,
        query: str,
        limit: int,
    ) -> list[KnowledgeEvidence]:
        hits = await self.vector_store.search(
            tenant_id=scope.tenant_id,
            query=query,
            limit=limit,
        )
        if not hits:
            return []
        async with self.session_factory() as session:
            repository = KnowledgeRepository(session)
            documents = await repository.get_documents_by_ids(
                scope=scope,
                document_ids=[hit.document_id for hit in hits],
            )
        documents_by_id = {document.id: document for document in documents}

        evidence: list[KnowledgeEvidence] = []
        seen_document_ids: set[UUID] = set()
        for hit in hits:
            document = documents_by_id.get(hit.document_id)
            if document is None or hit.document_id in seen_document_ids:
                continue
            seen_document_ids.add(hit.document_id)
            evidence.append(
                KnowledgeEvidence(
                    document_id=document.id,
                    external_document_id=document.external_document_id,
                    title=document.title,
                    source_uri=document.source_uri,
                    content_snippet=hit.content_snippet,
                    score=hit.score,
                )
            )
        postgres_evidence = await self._retrieve_from_postgres(
            scope=scope,
            query=query,
            limit=limit,
        )
        return merge_evidence(evidence, postgres_evidence, limit=limit)

    async def _retrieve_from_postgres(
        self,
        *,
        scope: TenantScope,
        query: str,
        limit: int,
    ) -> list[KnowledgeEvidence]:
        async with self.session_factory() as session:
            repository = KnowledgeRepository(session)
            documents = await repository.search_documents(
                scope=scope,
                query=query,
                limit=limit,
            )
        return [
            KnowledgeEvidence(
                document_id=document.id,
                external_document_id=document.external_document_id,
                title=document.title,
                source_uri=document.source_uri,
                content_snippet=None,
                score=None,
            )
            for document in documents
        ]


__all__ = ["ConsultationKnowledgeRetriever"]
