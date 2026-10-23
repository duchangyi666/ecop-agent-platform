from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.agent.state import KnowledgeEvidence
from backend.database.base import TenantScope
from backend.rag.retriever import ConsultationKnowledgeRetriever


@pytest.mark.asyncio
async def test_vector_miss_falls_back_to_postgres(monkeypatch) -> None:
    scope = TenantScope(tenant_id=uuid4())
    postgres_evidence = [
        KnowledgeEvidence(
            document_id=uuid4(),
            external_document_id="postgres-fallback",
            title="PostgreSQL fallback result",
        )
    ]
    vector_store = AsyncMock()
    vector_store.search.return_value = []
    retriever = ConsultationKnowledgeRetriever(
        session_factory=object(),
        vector_store=vector_store,
    )
    postgres_search = AsyncMock(return_value=postgres_evidence)
    monkeypatch.setattr(retriever, "_retrieve_from_postgres", postgres_search)

    result = await retriever.retrieve(scope=scope, query="refund policy", limit=5)

    assert result == postgres_evidence
    vector_store.search.assert_awaited_once_with(
        tenant_id=scope.tenant_id,
        query="refund policy",
        limit=5,
    )
    postgres_search.assert_awaited_once_with(
        scope=scope,
        query="refund policy",
        limit=5,
    )


@pytest.mark.asyncio
async def test_negative_vector_score_is_clamped(monkeypatch) -> None:
    scope = TenantScope(tenant_id=uuid4())
    document_id = uuid4()
    vector_store = AsyncMock()
    vector_store.search.return_value = [
        SimpleNamespace(
            document_id=document_id,
            content_snippet="refund policy",
            score=-0.04,
        )
    ]

    document = SimpleNamespace(
        id=document_id,
        external_document_id="doc-negative-score",
        title="Refund policy",
        source_uri=None,
    )

    class _FakeRepository:
        def __init__(self, session) -> None:
            del session

        async def get_documents_by_ids(self, *, scope, document_ids):
            del scope, document_ids
            return [document]

    class _FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr("backend.rag.retriever.KnowledgeRepository", _FakeRepository)
    retriever = ConsultationKnowledgeRetriever(
        session_factory=lambda: _FakeSession(),
        vector_store=vector_store,
    )
    monkeypatch.setattr(
        retriever,
        "_retrieve_from_postgres",
        AsyncMock(return_value=[]),
    )

    result = await retriever.retrieve(scope=scope, query="refund", limit=5)

    assert len(result) == 1
    assert result[0].score is not None
    assert result[0].score >= 0.0
