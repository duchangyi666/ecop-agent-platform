from __future__ import annotations

from uuid import uuid4

import pytest

from backend.agent.state import KnowledgeEvidence
from backend.agent.tools.knowledge import KnowledgeDocumentResult
from backend.rag.reranker import (
    DeterministicDocumentReranker,
    DeterministicReranker,
)


@pytest.mark.asyncio
async def test_deterministic_reranker_sorts_evidence_by_score() -> None:
    low = KnowledgeEvidence(
        document_id=uuid4(),
        external_document_id="low",
        title="Low",
        score=0.1,
    )
    high = KnowledgeEvidence(
        document_id=uuid4(),
        external_document_id="high",
        title="High",
        score=0.9,
    )

    ranked = await DeterministicReranker().rerank(
        query="query",
        candidates=[low, high],
    )

    assert ranked == [high, low]


@pytest.mark.asyncio
async def test_deterministic_document_reranker_sorts_by_score() -> None:
    def result(score: float | None, title: str) -> KnowledgeDocumentResult:
        return KnowledgeDocumentResult(
            document_id=uuid4(),
            title=title,
            external_document_id=title,
            source_uri=None,
            status="active",
            visibility="tenant",
            score=score,
        )

    ranked = await DeterministicDocumentReranker().rerank(
        query="query",
        candidates=[result(None, "none"), result(0.8, "high")],
    )

    assert ranked[0].title == "high"
    assert ranked[1].title == "none"
