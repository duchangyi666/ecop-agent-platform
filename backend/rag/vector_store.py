from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from backend.database.models.governance import Document
from backend.database.models.knowledge import KnowledgeChunk
from backend.rag.config import RAGSettings, get_rag_settings
from backend.rag.embedder import TextEmbedder, create_embedder


@dataclass(frozen=True, slots=True)
class KnowledgeVectorHit:
    document_id: UUID
    chunk_id: UUID
    external_document_id: str
    title: str
    source_uri: str | None
    content_snippet: str
    score: float


class KnowledgeVectorStore(Protocol):
    async def upsert_document_chunks(
        self,
        *,
        tenant_id: UUID,
        document: Document,
        chunks: list[KnowledgeChunk],
    ) -> None: ...

    async def search(
        self,
        *,
        tenant_id: UUID,
        query: str,
        limit: int,
    ) -> list[KnowledgeVectorHit]: ...

    async def delete_document_chunks(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> None: ...

    async def close(self) -> None: ...


class MilvusKnowledgeVectorStore:
    def __init__(
        self,
        *,
        uri: str,
        collection_name: str,
        embedder: TextEmbedder,
        timeout: float = 10.0,
    ) -> None:
        from pymilvus import DataType, MilvusClient

        self._collection = collection_name
        self._embedder = embedder
        self._dimension = embedder.dimension
        self._data_type = DataType
        self._client = MilvusClient(uri=uri, timeout=timeout)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if not self._client.has_collection(self._collection):
            schema = self._client.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field("pk", self._data_type.VARCHAR, is_primary=True, max_length=128)
            schema.add_field("tenant_id", self._data_type.VARCHAR, max_length=64)
            schema.add_field("document_id", self._data_type.VARCHAR, max_length=64)
            schema.add_field("chunk_id", self._data_type.VARCHAR, max_length=64)
            schema.add_field("external_document_id", self._data_type.VARCHAR, max_length=160)
            schema.add_field("title", self._data_type.VARCHAR, max_length=512)
            schema.add_field("source_uri", self._data_type.VARCHAR, max_length=1000)
            schema.add_field("content", self._data_type.VARCHAR, max_length=12000)
            schema.add_field("embedding", self._data_type.FLOAT_VECTOR, dim=self._dimension)
            index_params = self._client.prepare_index_params()
            index_params.add_index(
                "embedding",
                index_type="AUTOINDEX",
                metric_type="COSINE",
            )
            self._client.create_collection(
                self._collection,
                schema=schema,
                index_params=index_params,
            )

        load_state = self._client.get_load_state(self._collection).get("state")
        if getattr(load_state, "name", str(load_state)) != "Loaded":
            self._client.load_collection(self._collection)

    async def upsert_document_chunks(
        self,
        *,
        tenant_id: UUID,
        document: Document,
        chunks: list[KnowledgeChunk],
    ) -> None:
        if not chunks:
            return
        rows = [
            {
                "pk": str(chunk.id),
                "tenant_id": str(tenant_id),
                "document_id": str(document.id),
                "chunk_id": str(chunk.id),
                "external_document_id": document.external_document_id,
                "title": document.title,
                "source_uri": document.source_uri or "",
                "content": chunk.content,
                "embedding": vector,
            }
            for chunk, vector in zip(chunks, await self._embed(chunks))
        ]
        await asyncio.to_thread(self._client.upsert, self._collection, rows)

    async def search(
        self,
        *,
        tenant_id: UUID,
        query: str,
        limit: int,
    ) -> list[KnowledgeVectorHit]:
        embedding = (await self._embed([query]))[0]
        raw_results = await asyncio.to_thread(
            self._client.search,
            self._collection,
            data=[embedding],
            limit=limit,
            filter=f'tenant_id == "{tenant_id}"',
            output_fields=[
                "document_id",
                "chunk_id",
                "external_document_id",
                "title",
                "source_uri",
                "content",
            ],
            search_params={"metric_type": "COSINE"},
            consistency_level="Strong",
        )
        hits: list[KnowledgeVectorHit] = []
        for hit in raw_results[0]:
            entity = hit.get("entity", {})
            hits.append(
                KnowledgeVectorHit(
                    document_id=UUID(entity["document_id"]),
                    chunk_id=UUID(entity["chunk_id"]),
                    external_document_id=entity["external_document_id"],
                    title=entity["title"],
                    source_uri=entity.get("source_uri") or None,
                    content_snippet=entity.get("content", "")[:300],
                    score=float(hit.get("distance", 0.0)),
                )
            )
        return hits

    async def delete_document_chunks(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> None:
        expression = f'tenant_id == "{tenant_id}" and document_id == "{document_id}"'
        await asyncio.to_thread(self._client.delete, self._collection, expression)

    async def close(self) -> None:
        await asyncio.to_thread(self._client.close)

    async def drop_collection(self) -> None:
        await asyncio.to_thread(self._client.drop_collection, self._collection)

    async def _embed(self, chunks: list[KnowledgeChunk] | list[str]) -> list[list[float]]:
        texts = [item.content if isinstance(item, KnowledgeChunk) else item for item in chunks]
        return await asyncio.to_thread(self._embedder.embed, texts)


def create_knowledge_vector_store(
    settings: RAGSettings | None = None,
    embedder: TextEmbedder | None = None,
) -> MilvusKnowledgeVectorStore | None:
    resolved = settings or get_rag_settings()
    if not resolved.milvus_uri:
        return None
    return MilvusKnowledgeVectorStore(
        uri=resolved.milvus_uri,
        collection_name=resolved.milvus_collection,
        embedder=embedder or create_embedder(resolved),
        timeout=resolved.milvus_timeout,
    )


__all__ = [
    "KnowledgeVectorHit",
    "KnowledgeVectorStore",
    "MilvusKnowledgeVectorStore",
    "create_knowledge_vector_store",
]
