from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.dependencies import (
    RequestContext,
    get_knowledge_vector_store,
    get_session_factory_dependency,
    require_permission,
)
from backend.api.schemas import (
    EvaluationRunItem,
    EvaluationRunListResponse,
    EvaluationRunRequest,
    EvaluationRunResponse,
)
from backend.database.unit_of_work import UnitOfWork
from backend.evaluation.runner import EvaluationRunner
from backend.rag.config import get_rag_settings
from backend.rag.reranker import create_reranker
from backend.rag.retriever import ConsultationKnowledgeRetriever
from backend.rag.vector_store import KnowledgeVectorStore

router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])


@router.get("", response_model=EvaluationRunListResponse)
async def list_evaluation_runs(
    context: RequestContext = Depends(require_permission("evaluation.read")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> EvaluationRunListResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        runs = await uow.evaluation.list_runs(
            scope=context.scope,
            limit=50,
        )
    return EvaluationRunListResponse(
        request_id=context.request_id,
        runs=[
            EvaluationRunItem(
                run_id=run.id,
                dataset_id=run.dataset_id,
                status=run.status,
                metrics=run.metrics,
                started_at=run.started_at,
                finished_at=run.finished_at,
            )
            for run in runs
        ],
    )


@router.post("/run", response_model=EvaluationRunResponse)
async def run_retrieval_evaluation(
    payload: EvaluationRunRequest,
    context: RequestContext = Depends(require_permission("evaluation.run")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
    vector_store: KnowledgeVectorStore | None = Depends(get_knowledge_vector_store),
) -> EvaluationRunResponse:
    retriever = ConsultationKnowledgeRetriever(
        session_factory,
        vector_store=vector_store,
        reranker=create_reranker(get_rag_settings()),
    )
    result = await EvaluationRunner(
        session_factory,
        retriever=retriever,
    ).run_retrieval_evaluation(
        scope=context.scope,
        dataset_code=payload.dataset_code,
        limit=payload.limit,
    )
    return EvaluationRunResponse.from_result(
        request_id=context.request_id,
        result=result,
    )


__all__ = ["router"]
