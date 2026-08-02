from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.knowledge_workflow import (
    KnowledgeWorkflowRequest,
    KnowledgeWorkflowService,
)
from backend.rag.ingestion import KnowledgeIngestRequest, KnowledgeIngestService
from backend.rag.config import get_rag_settings
from backend.rag.reranker import create_document_reranker
from backend.agent.state import create_agent_state
from backend.api.dependencies import (
    RequestContext,
    get_knowledge_vector_store,
    get_session_factory_dependency,
    require_permission,
)
from backend.api.schemas import KnowledgeIngestResponse, KnowledgeSearchResponse
from backend.rag.vector_store import KnowledgeVectorStore

router = APIRouter(prefix="/api/v1", tags=["knowledge"])


@router.get("/knowledge/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    response: Response,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    thread_id: Annotated[str | None, Query(max_length=120)] = None,
    context: RequestContext = Depends(require_permission("knowledge.search")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
    vector_store: KnowledgeVectorStore | None = Depends(get_knowledge_vector_store),
) -> KnowledgeSearchResponse:
    resolved_thread_id = thread_id or f"knowledge-{uuid4().hex}"
    result = await KnowledgeWorkflowService(
        session_factory,
        vector_store=vector_store,
        document_reranker=create_document_reranker(get_rag_settings()),
    ).run(
        KnowledgeWorkflowRequest(
            thread_id=resolved_thread_id,
            state=create_agent_state(
                scope=context.scope,
                request_id=uuid4(),
                message="知识库查询",
            ),
            query=q,
            limit=limit,
        )
    )

    if result.status == "blocked":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "security_blocked",
                "message": result.final_response,
            },
        )
    if result.status == "out_of_scope":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "out_of_scope",
                "message": result.final_response,
            },
        )
    if result.status == "human_handoff":
        response.status_code = status.HTTP_202_ACCEPTED

    return KnowledgeSearchResponse.from_result(request_id=context.request_id, result=result)


@router.post("/knowledge/documents", response_model=KnowledgeIngestResponse, status_code=201)
async def ingest_knowledge_document(
    payload: KnowledgeIngestRequest,
    context: RequestContext = Depends(require_permission("knowledge.ingest")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
    vector_store: KnowledgeVectorStore | None = Depends(get_knowledge_vector_store),
) -> KnowledgeIngestResponse:
    result = await KnowledgeIngestService(
        session_factory,
        vector_store=vector_store,
    ).run(
        scope=context.scope,
        request=payload,
    )
    return KnowledgeIngestResponse.from_result(request_id=context.request_id, result=result)


__all__ = ["router"]
