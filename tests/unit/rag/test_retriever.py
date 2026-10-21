from __future__ import annotations

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
