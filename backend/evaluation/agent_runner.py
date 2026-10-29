from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.agents.customer_service import _prompt_messages
from backend.agent.guards import DomainGuard, InputSecurityGuard
from backend.agent.state import ConversationMessage
from backend.database.base import TenantScope
from backend.database.unit_of_work import UnitOfWork
from backend.domain.common import DomainError
from backend.evaluation.agent_metrics import accuracy, classification_metrics, guard_metrics
from backend.evaluation.judge import AnswerJudge
from backend.evaluation.metrics import compute_retrieval_metrics
from backend.evaluation.runner import EvaluationRunResult
from backend.llm.contracts import ResponseDraft
from backend.llm.gateway import ModelGateway
from backend.rag.retriever import ConsultationKnowledgeRetriever

_QA_KIND = "qa"
_GUARD_KIND = "guard"


@dataclass(frozen=True, slots=True)
class _CaseMetrics:
    metrics: dict[str, float]
    passed: bool = False
    domain_evaluated: bool = False
    expected_status: str | None = None
    actual_status: str | None = None
    expected_blocked: bool | None = None
    actual_blocked: bool | None = None


class AgentEvaluationRunner:
    """Agent-level evaluations beyond retrieval.

    - correctness: end-to-end QA evaluation (retrieve -> generate -> judge),
      aligned with the EduAgent Answer Correctness methodology.
    - guard: deterministic security boundary evaluation (interception rate,
      false positive rate, false negative rate) and domain classification.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        retriever: ConsultationKnowledgeRetriever,
        model_gateway: ModelGateway,
    ) -> None:
        self.session_factory = session_factory
        self.retriever = retriever
        self.model_gateway = model_gateway

    async def run_correctness_evaluation(
        self,
        *,
        scope: TenantScope,
        dataset_code: str,
        limit: int = 5,
        max_cases: int | None = None,
    ) -> EvaluationRunResult:
        if max_cases is not None and max_cases < 1:
            raise ValueError("max_cases must be positive")
        judge = AnswerJudge(self.model_gateway)
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            dataset = await uow.evaluation.get_dataset_by_code(
                scope=scope,
                dataset_code=dataset_code,
            )
            if dataset is None:
                raise DomainError("evaluation dataset not found in tenant scope")
            cases = [
                case
                for case in await uow.evaluation.list_cases(
                    scope=scope,
                    dataset_id=dataset.id,
                )
                if case.expected_summary.get("kind") == _QA_KIND
            ]
            if max_cases is not None:
                cases = cases[:max_cases]
            if not cases:
                raise DomainError("evaluation dataset has no qa cases")

            run = await uow.evaluation.create_run(
                scope=scope,
                dataset_id=dataset.id,
            )
            per_case: list[_CaseMetrics] = []
            for case in cases:
                query = case.input_summary
                expected = case.expected_summary
                gold_answer = str(expected.get("gold_answer", ""))
                gold_document_ids = {
                    str(item)
                    for item in expected.get("document_ids", [])
                }

                evidence = await self.retriever.retrieve(
                    scope=scope,
                    query=query,
                    limit=limit,
                )
                metrics: dict[str, float] = {}
                if gold_document_ids:
                    retrieved_ids = [str(item.document_id) for item in evidence]
                    retrieval = compute_retrieval_metrics(
                        gold_document_ids,
                        retrieved_ids,
                        k=limit,
                    )
                    metrics["recall_at_k"] = retrieval["recall_at_k"]
                    metrics["mrr"] = retrieval["mrr"]

                agent_answer = await self._generate_answer(query, evidence)
                verdict = await judge.judge(
                    question=query,
                    gold_answer=gold_answer,
                    agent_answer=agent_answer,
                )
                judge_error = verdict is None
                correctness = 1.0 if (verdict is not None and verdict.verdict == "correct") else 0.0
                metrics["correctness"] = correctness
                metrics["judge_error"] = 1.0 if judge_error else 0.0

                passed = correctness > 0 and (not gold_document_ids or metrics.get("recall_at_k", 0.0) > 0)
                per_case.append(_CaseMetrics(metrics=metrics, passed=passed))
                await uow.evaluation.add_result(
                    scope=scope,
                    run_id=run.id,
                    case_id=case.id,
                    score=correctness,
                    passed=passed,
                    metrics=metrics,
                    result_summary=(
                        f"correctness={correctness:.2f}, judge_error={int(judge_error)}, "
                        f"recall={metrics.get('recall_at_k', 0.0):.3f}"
                    ),
                )

            aggregated = {
                "kind": "correctness",
                "case_count": len(per_case),
                "passed_count": sum(1 for c in per_case if c.passed),
                "correctness": fmean([c.metrics["correctness"] for c in per_case]),
                "judge_error_count": sum(1 for c in per_case if c.metrics.get("judge_error", 0.0) > 0),
            }
            recall_values = [
                c.metrics["recall_at_k"] for c in per_case if "recall_at_k" in c.metrics
            ]
            if recall_values:
                aggregated["recall_at_k"] = fmean(recall_values)
            await uow.evaluation.complete_run(
                scope=scope,
                run_id=run.id,
                metrics=aggregated,
            )

        return EvaluationRunResult(
            run_id=run.id,
            dataset_code=dataset_code,
            case_count=len(per_case),
            metrics=aggregated,
        )

    async def run_guard_evaluation(
        self,
        *,
        scope: TenantScope,
        dataset_code: str,
        limit: int = 5,
        max_cases: int | None = None,
    ) -> EvaluationRunResult:
        if max_cases is not None and max_cases < 1:
            raise ValueError("max_cases must be positive")
        input_guard = InputSecurityGuard()
        domain_guard = DomainGuard()
        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            dataset = await uow.evaluation.get_dataset_by_code(
                scope=scope,
                dataset_code=dataset_code,
            )
            if dataset is None:
                raise DomainError("evaluation dataset not found in tenant scope")
            cases = [
                case
                for case in await uow.evaluation.list_cases(
                    scope=scope,
                    dataset_id=dataset.id,
                )
                if case.expected_summary.get("kind") == _GUARD_KIND
            ]
            if max_cases is not None:
                cases = cases[:max_cases]
            if not cases:
                raise DomainError("evaluation dataset has no guard cases")

            run = await uow.evaluation.create_run(
                scope=scope,
                dataset_id=dataset.id,
            )
            per_case: list[_CaseMetrics] = []
            for case in cases:
                query = case.input_summary
                expected = case.expected_summary
                expected_status = str(expected.get("expect", "allow"))
                decision = input_guard.evaluate(query)
                actual_status = decision.status

                # Binary view: block / human_handoff count as "blocked".
                expected_blocked = expected_status != "allow"
                actual_blocked = actual_status != "allow"
                status_hit = 1.0 if actual_status == expected_status else 0.0
                domain_hit = 0.0
                expected_domain = expected.get("domain")
                domain_evaluated = expected_status == "allow" and bool(expected_domain)
                if domain_evaluated:
                    domain_decision = domain_guard.evaluate(query)
                    domain_hit = 1.0 if (
                        domain_decision.status == "in_scope"
                        and domain_decision.domain == expected_domain
                    ) else 0.0

                metrics = {
                    "status_hit": status_hit,
                    "domain_hit": domain_hit,
                    "blocked": 1.0 if actual_blocked else 0.0,
                }
                passed = status_hit > 0 and (not domain_evaluated or domain_hit > 0)
                per_case.append(
                    _CaseMetrics(
                        metrics=metrics,
                        passed=passed,
                        domain_evaluated=domain_evaluated,
                        expected_status=expected_status,
                        actual_status=actual_status,
                        expected_blocked=expected_blocked,
                        actual_blocked=actual_blocked,
                    )
                )
                await uow.evaluation.add_result(
                    scope=scope,
                    run_id=run.id,
                    case_id=case.id,
                    score=status_hit,
                    passed=passed,
                    metrics={
                        **metrics,
                        "expected_status": expected_status,
                        "actual_status": actual_status,
                    },
                    result_summary=(
                        f"expected={expected_status}, actual={actual_status}, "
                        f"status_hit={int(status_hit)}, domain_hit={int(domain_hit)}"
                    ),
                )

            aggregated: dict[str, object] = {
                "kind": "guard",
                "case_count": len(per_case),
                "passed_count": sum(1 for c in per_case if c.passed),
                "status_accuracy": accuracy(
                    [str(c.actual_status) for c in per_case],
                    [str(c.expected_status) for c in per_case],
                ),
            }
            binary = guard_metrics(
                [bool(c.expected_blocked) for c in per_case],
                [bool(c.actual_blocked) for c in per_case],
            )
            aggregated.update(binary)
            domain_cases = [c for c in per_case if c.domain_evaluated]
            domain_hits = [c.metrics["domain_hit"] for c in domain_cases]
            if domain_hits:
                aggregated["domain_accuracy"] = fmean(domain_hits)
            await uow.evaluation.complete_run(
                scope=scope,
                run_id=run.id,
                metrics=aggregated,
            )

        return EvaluationRunResult(
            run_id=run.id,
            dataset_code=dataset_code,
            case_count=len(per_case),
            metrics=aggregated,
        )

    async def _generate_answer(
        self,
        query: str,
        evidence,
    ) -> str:
        conversation = [ConversationMessage(role="user", content=query)]
        system_prompt, user_prompt = _prompt_messages(
            conversation,
            knowledge_evidence=evidence,
        )
        try:
            draft, _ = await self.model_gateway.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=ResponseDraft,
            )
            if isinstance(draft, ResponseDraft):
                return draft.answer
            return ResponseDraft.model_validate(draft.model_dump()).answer
        except Exception:
            return ""


__all__ = ["AgentEvaluationRunner"]
