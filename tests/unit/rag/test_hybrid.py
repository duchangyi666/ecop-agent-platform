from __future__ import annotations

from uuid import uuid4

from backend.agent.state import KnowledgeEvidence
from backend.agent.tools.knowledge import KnowledgeDocumentResult
from backend.rag.hybrid import merge_document_results, merge_evidence


def test_merge_evidence_combines_vector_and_postgres_with_rrf() -> None:
    first_id = uuid4()
    second_id = uuid4()
    third_id = uuid4()
    vector_evidence = [
        KnowledgeEvidence(
            document_id=first_id,
            external_document_id="first",
            title="第一份政策",
            content_snippet="向量摘要一",
            score=0.9,
        ),
        KnowledgeEvidence(
            document_id=second_id,
            external_document_id="second",
            title="第二份政策",
            content_snippet="向量摘要二",
            score=0.8,
        ),
    ]
    postgres_evidence = [
        KnowledgeEvidence(
            document_id=second_id,
            external_document_id="second",
            title="第二份政策",
        ),
        KnowledgeEvidence(
            document_id=third_id,
            external_document_id="third",
            title="第三份政策",
        ),
    ]

    merged = merge_evidence(vector_evidence, postgres_evidence, limit=3)

    assert [item.document_id for item in merged] == [second_id, first_id, third_id]
    assert merged[0].content_snippet == "向量摘要二"
    assert merged[0].score is not None
    assert merged[0].score > merged[1].score


def test_merge_document_results_dedupes_and_keeps_vector_snippet() -> None:
    document_id = uuid4()
    vector_results = [
        KnowledgeDocumentResult(
            document_id=document_id,
            title="退款政策",
            external_document_id="refund-policy",
            source_uri="https://docs.example.com/refund-policy",
            status="active",
            visibility="tenant",
            content_snippet="向量摘要",
            score=0.9,
        )
    ]
    postgres_results = [
        KnowledgeDocumentResult(
            document_id=document_id,
            title="退款政策",
            external_document_id="refund-policy",
            source_uri="https://docs.example.com/refund-policy",
            status="active",
            visibility="tenant",
        )
    ]

    merged = merge_document_results(vector_results, postgres_results, limit=5)

    assert len(merged) == 1
    assert merged[0].content_snippet == "向量摘要"
    assert merged[0].score is not None
