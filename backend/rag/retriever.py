from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.state import KnowledgeEvidence
from backend.database.base import TenantScope
from backend.database.repositories.knowledge import KnowledgeRepository
from backend.rag.hybrid import merge_evidence
from backend.rag.reranker import KnowledgeReranker
from backend.rag.vector_store import KnowledgeVectorStore


def _bounded_score(score: float | None) -> float | None:
    """Clamp cosine similarity into the documented 0..1 evidence range.

    Milvus COSINE can return values slightly below 0 for unrelated vectors;
    KnowledgeEvidence rejects negative scores, which used to abort the whole
    retrieval and silently return empty evidence. Clamp instead of failing.
    """

    if score is None:
        return None
    return max(0.0, min(1.0, score))


class ConsultationKnowledgeRetriever:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None,
        vector_store: KnowledgeVectorStore | None = None,
        reranker: KnowledgeReranker | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.vector_store = vector_store
        self.reranker = reranker

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
            evidence = await self._retrieve_from_vector(
                scope=scope,
                query=normalized,
                limit=limit,
            )
        else:
            evidence = await self._retrieve_from_postgres(
                scope=scope,
                query=normalized,
                limit=limit,
            )
        if self.reranker is not None:
            evidence = await self.reranker.rerank(
                query=normalized,
                candidates=evidence,
            )
        return evidence

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
        postgres_evidence = await self._retrieve_from_postgres(
            scope=scope,
            query=query,
            limit=limit,
        )
        if not hits:
            return postgres_evidence
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
                    score=_bounded_score(hit.score),
                )
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
