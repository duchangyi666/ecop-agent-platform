from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.database.base import TenantScope
from backend.database.models.governance import (
    Document,
    EvaluationResult,
    EvaluationRun,
)
from backend.database.repositories.evaluation import EvaluationRepository
from backend.evaluation.runner import EvaluationRunner
from backend.rag.retriever import ConsultationKnowledgeRetriever


async def _seed_document(session_factory, tenant_id, *, title: str) -> Document:
    document = Document(
        id=uuid4(),
        tenant_id=tenant_id,
        external_document_id=f"eval-{uuid4().hex[:8]}",
        title=title,
        status="active",
        source_uri=f"https://docs.example.com/{title}",
        visibility="tenant",
    )
    async with session_factory() as session:
        session.add(document)
        await session.commit()
    return document


@pytest.mark.asyncio
async def test_evaluation_runner_calculates_retrieval_metrics(
    session_factory,
    tenant_a,
) -> None:
    refund_document = await _seed_document(
        session_factory,
        tenant_a.id,
        title="退款政策",
    )
    ticket_document = await _seed_document(
        session_factory,
        tenant_a.id,
        title="工单处理规范",
    )
    scope = TenantScope(tenant_id=tenant_a.id)

    async with session_factory() as session:
        repository = EvaluationRepository(session)
        dataset = await repository.create_dataset(
            scope=scope,
            dataset_code="retrieval-demo",
            name="Retrieval Demo",
        )
        await repository.create_case(
            scope=scope,
            dataset_id=dataset.id,
            case_key="refund",
            input_summary="退款",
            expected_summary={"document_ids": [str(refund_document.id)]},
            tags=["retrieval"],
        )
        await repository.create_case(
            scope=scope,
            dataset_id=dataset.id,
            case_key="ticket",
            input_summary="工单",
            expected_summary={"document_ids": [str(ticket_document.id)]},
            tags=["retrieval"],
        )
        await session.commit()

    runner = EvaluationRunner(
        session_factory,
        retriever=ConsultationKnowledgeRetriever(session_factory),
    )
    result = await runner.run_retrieval_evaluation(
        scope=scope,
        dataset_code="retrieval-demo",
        limit=5,
    )

    assert result.case_count == 2
    assert result.metrics["case_count"] == 2
    assert result.metrics["passed_count"] == 2
    assert result.metrics["recall_at_k"] > 0

    async with session_factory() as session:
        run = await session.get(EvaluationRun, result.run_id)
        result_count = await session.scalar(
            select(func.count(EvaluationResult.id)).where(
                EvaluationResult.run_id == result.run_id,
            )
        )

    assert run is not None
    assert run.status == "completed"
    assert result_count == 2
