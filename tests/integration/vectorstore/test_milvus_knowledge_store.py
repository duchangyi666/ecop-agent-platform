from __future__ import annotations

from uuid import uuid4

import pytest

from backend.database.models.governance import Document
from backend.database.models.knowledge import KnowledgeChunk
from backend.rag.config import get_rag_settings
from backend.rag.embedder import DeterministicEmbedder
from backend.rag.vector_store import MilvusKnowledgeVectorStore


pytestmark = pytest.mark.skipif(
    not get_rag_settings().milvus_uri,
    reason="MILVUS_URI is not configured",
)


@pytest.mark.asyncio
async def test_milvus_store_indexes_and_searches_with_tenant_filter() -> None:
    settings = get_rag_settings()
    collection_name = f"ecop_test_{uuid4().hex[:8]}"
    tenant_a = uuid4()
    tenant_b = uuid4()
    document_id = uuid4()
    chunk_id = uuid4()
    document = Document(
        id=document_id,
        tenant_id=tenant_a,
        external_document_id="refund-policy",
        title="退款政策",
        status="active",
        source_uri="https://docs.example.com/refund-policy",
        visibility="tenant",
    )
    chunk = KnowledgeChunk(
        id=chunk_id,
        tenant_id=tenant_a,
        document_id=document_id,
        chunk_number=1,
        content="同一账单在二十四小时内重复扣费可以申请退款。",
        content_hash="hash",
        token_count=20,
        status="active",
    )
    store = MilvusKnowledgeVectorStore(
        uri=settings.milvus_uri,
        collection_name=collection_name,
        embedder=DeterministicEmbedder(dimension=32),
        timeout=settings.milvus_timeout,
    )
    try:
        await store.upsert_document_chunks(
            tenant_id=tenant_a,
            document=document,
            chunks=[chunk],
        )

        hits = await store.search(
            tenant_id=tenant_a,
            query="重复扣费退款",
            limit=5,
        )
        cross_tenant_hits = await store.search(
            tenant_id=tenant_b,
            query="重复扣费退款",
            limit=5,
        )

        assert len(hits) == 1
        assert hits[0].document_id == document_id
        assert hits[0].title == "退款政策"
        assert cross_tenant_hits == []
    finally:
        await store.drop_collection()
        await store.close()
