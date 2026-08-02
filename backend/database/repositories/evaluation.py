from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select

from backend.database.base import TenantScope, utc_now
from backend.database.models.governance import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationResult,
    EvaluationRun,
)
from backend.database.repositories.base import TenantScopedRepository


class EvaluationRepository(TenantScopedRepository):
    async def get_dataset_by_code(
        self,
        *,
        scope: TenantScope,
        dataset_code: str,
    ) -> EvaluationDataset | None:
        statement = self._tenant_visible(
            select(EvaluationDataset),
            EvaluationDataset,
            scope=scope,
        ).where(EvaluationDataset.dataset_code == dataset_code)
        return await self.session.scalar(statement)

    async def create_dataset(
        self,
        *,
        scope: TenantScope,
        dataset_code: str,
        name: str,
    ) -> EvaluationDataset:
        dataset = EvaluationDataset(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            dataset_code=dataset_code,
            name=name,
            status="active",
        )
        self.session.add(dataset)
        await self.session.flush()
        return dataset

    async def create_case(
        self,
        *,
        scope: TenantScope,
        dataset_id: UUID,
        case_key: str,
        input_summary: str,
        expected_summary: dict[str, Any],
        tags: list[str] | None = None,
    ) -> EvaluationCase:
        case = EvaluationCase(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            dataset_id=dataset_id,
            case_key=case_key,
            input_summary=input_summary,
            expected_summary=expected_summary,
            tags=tags or [],
        )
        self.session.add(case)
        await self.session.flush()
        return case

    async def list_cases(
        self,
        *,
        scope: TenantScope,
        dataset_id: UUID,
    ) -> list[EvaluationCase]:
        statement = (
            self._tenant_visible(
                select(EvaluationCase),
                EvaluationCase,
                scope=scope,
            )
            .where(EvaluationCase.dataset_id == dataset_id)
            .order_by(EvaluationCase.case_key)
        )
        return list(await self.session.scalars(statement))

    async def create_run(
        self,
        *,
        scope: TenantScope,
        dataset_id: UUID,
        agent_version_id: UUID | None = None,
    ) -> EvaluationRun:
        run = EvaluationRun(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            dataset_id=dataset_id,
            agent_version_id=agent_version_id,
            status="running",
            metrics={},
            started_at=utc_now(),
            finished_at=None,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def add_result(
        self,
        *,
        scope: TenantScope,
        run_id: UUID,
        case_id: UUID,
        score: float,
        passed: bool,
        metrics: dict[str, Any],
        result_summary: str | None,
    ) -> EvaluationResult:
        result = EvaluationResult(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            run_id=run_id,
            case_id=case_id,
            score=Decimal(f"{score:.2f}"),
            passed=passed,
            metrics=metrics,
            result_summary=result_summary,
        )
        self.session.add(result)
        await self.session.flush()
        return result

    async def complete_run(
        self,
        *,
        scope: TenantScope,
        run_id: UUID,
        metrics: dict[str, Any],
    ) -> EvaluationRun:
        statement = self._tenant_visible(
            select(EvaluationRun),
            EvaluationRun,
            scope=scope,
        ).where(EvaluationRun.id == run_id)
        run = await self.session.scalar(statement)
        if run is None:
            raise ValueError("evaluation run not found in tenant scope")
        run.status = "completed"
        run.metrics = metrics
        run.finished_at = datetime.now(timezone.utc)
        await self.session.flush()
        return run

    async def list_runs(
        self,
        *,
        scope: TenantScope,
        limit: int = 50,
    ) -> list[EvaluationRun]:
        statement = (
            self._tenant_visible(
                select(EvaluationRun),
                EvaluationRun,
                scope=scope,
            )
            .order_by(EvaluationRun.started_at.desc())
            .limit(limit)
        )
        return list(await self.session.scalars(statement))


__all__ = ["EvaluationRepository"]
