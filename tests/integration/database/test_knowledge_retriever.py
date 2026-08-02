from __future__ import annotations

from uuid import uuid4

import pytest

from backend.database.base import TenantScope
from backend.database.models.governance import Document
from backend.rag.retriever import ConsultationKnowledgeRetriever
from backend.rag.vector_store import KnowledgeVectorHit


async def _add_document(session_factory, tenant_id, *, external_document_id: str, title: str) -> Document:
    document = Document(
        id=uuid4(),
        tenant_id=tenant_id,
        external_document_id=external_document_id,
        title=title,
        status="active",
        source_uri=f"https://docs.example.com/{external_document_id}",
        visibility="tenant",
    )
    async with session_factory() as session:
        session.add(document)
        await session.commit()
    return document


class FakeVectorStore:
    def __init__(self, hits: list[KnowledgeVectorHit]) -> None:
        self.hits = hits

    async def search(self, **kwargs) -> list[KnowledgeVectorHit]:
        return self.hits

    async def upsert_document_chunks(self, **kwargs) -> None:
        return None

    async def delete_document_chunks(self, **kwargs) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_consultation_retriever_returns_tenant_scoped_postgres_evidence(
    session_factory,
    tenant_a,
    tenant_b,
) -> None:
    await _add_document(
        session_factory,
        tenant_a.id,
        external_document_id="refund-policy",
        title="退款政策",
    )
    retriever = ConsultationKnowledgeRetriever(session_factory)

    evidence = await retriever.retrieve(
        scope=TenantScope(tenant_id=tenant_a.id),
        query="退款",
        limit=5,
    )
    cross_tenant_evidence = await retriever.retrieve(
        scope=TenantScope(tenant_id=tenant_b.id),
        query="退款",
        limit=5,
    )

    assert len(evidence) == 1
    assert evidence[0].title == "退款政策"
    assert evidence[0].source_uri == "https://docs.example.com/refund-policy"
    assert cross_tenant_evidence == []


@pytest.mark.asyncio
async def test_consultation_retriever_uses_vector_snippet_and_tenant_metadata(
    session_factory,
    tenant_a,
) -> None:
    document = await _add_document(
        session_factory,
        tenant_a.id,
        external_document_id="sla-policy",
        title="服务等级政策",
    )
    await _add_document(
        session_factory,
        tenant_a.id,
        external_document_id="sla-policy-supplement",
        title="服务等级政策补充说明",
    )
    vector_store = FakeVectorStore(
        [
            KnowledgeVectorHit(
                document_id=document.id,
                chunk_id=uuid4(),
                external_document_id="sla-policy",
                title="服务等级政策",
                source_uri="https://docs.example.com/sla-policy",
                content_snippet="企业版服务等级目标为百分之九十九点九可用性。",
                score=0.9,
            )
        ]
    )
    retriever = ConsultationKnowledgeRetriever(session_factory, vector_store=vector_store)

    evidence = await retriever.retrieve(
        scope=TenantScope(tenant_id=tenant_a.id),
        query="服务等级",
        limit=5,
    )

    assert len(evidence) == 2
    assert evidence[0].document_id == document.id
    assert evidence[0].content_snippet == "企业版服务等级目标为百分之九十九点九可用性。"
    assert evidence[0].score is not None
