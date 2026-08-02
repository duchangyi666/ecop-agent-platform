from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.database.base import TenantScope
from backend.database.unit_of_work import UnitOfWork
from backend.domain.common import DomainError
from backend.evaluation.metrics import compute_retrieval_metrics
from backend.rag.retriever import ConsultationKnowledgeRetriever


@dataclass(frozen=True, slots=True)
class EvaluationRunResult:
    run_id: UUID
    dataset_code: str
    case_count: int
    metrics: dict[str, float]


class EvaluationRunner:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        retriever: ConsultationKnowledgeRetriever,
    ) -> None:
        self.session_factory = session_factory
        self.retriever = retriever

    async def run_retrieval_evaluation(
        self,
        *,
        scope: TenantScope,
        dataset_code: str,
        limit: int = 5,
    ) -> EvaluationRunResult:
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            dataset = await uow.evaluation.get_dataset_by_code(
                scope=scope,
                dataset_code=dataset_code,
            )
            if dataset is None:
                raise DomainError("evaluation dataset not found in tenant scope")
            cases = await uow.evaluation.list_cases(
                scope=scope,
                dataset_id=dataset.id,
            )
            if not cases:
                raise DomainError("evaluation dataset has no cases")

            run = await uow.evaluation.create_run(
                scope=scope,
                dataset_id=dataset.id,
            )
            per_case_metrics: list[dict[str, float]] = []
            for case in cases:
                evidence = await self.retriever.retrieve(
                    scope=scope,
                    query=case.input_summary,
                    limit=limit,
                )
                retrieved_ids = [str(item.document_id) for item in evidence]
                expected_ids = {
                    str(item)
                    for item in case.expected_summary.get("document_ids", [])
                }
                metrics = compute_retrieval_metrics(
                    expected_ids,
                    retrieved_ids,
                    k=limit,
                )
                passed = bool(expected_ids) and metrics["recall_at_k"] > 0
                per_case_metrics.append(metrics)
                await uow.evaluation.add_result(
                    scope=scope,
                    run_id=run.id,
                    case_id=case.id,
                    score=metrics["recall_at_k"],
                    passed=passed,
                    metrics=metrics,
                    result_summary=(
                        f"recall={metrics['recall_at_k']:.3f}, "
                        f"mrr={metrics['mrr']:.3f}"
                    ),
                )

            aggregated = {
                "case_count": len(per_case_metrics),
                "passed_count": sum(
                    1 for metrics in per_case_metrics if metrics["recall_at_k"] > 0
                ),
                "recall_at_k": fmean(
                    [metrics["recall_at_k"] for metrics in per_case_metrics]
                ),
                "precision_at_k": fmean(
                    [metrics["precision_at_k"] for metrics in per_case_metrics]
                ),
                "mrr": fmean([metrics["mrr"] for metrics in per_case_metrics]),
                "ndcg_at_k": fmean(
                    [metrics["ndcg_at_k"] for metrics in per_case_metrics]
                ),
            }
            await uow.evaluation.complete_run(
                scope=scope,
                run_id=run.id,
                metrics=aggregated,
            )

        return EvaluationRunResult(
            run_id=run.id,
            dataset_code=dataset_code,
            case_count=len(per_case_metrics),
            metrics=aggregated,
        )


__all__ = ["EvaluationRunResult", "EvaluationRunner"]
