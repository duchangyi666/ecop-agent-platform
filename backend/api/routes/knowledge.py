from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.knowledge_workflow import (
    KnowledgeWorkflowRequest,
    KnowledgeWorkflowService,
)
from backend.agent.state import create_agent_state
from backend.api.dependencies import (
    RequestContext,
    get_session_factory_dependency,
    require_permission,
)
from backend.api.schemas import KnowledgeSearchResponse

router = APIRouter(prefix="/api/v1", tags=["knowledge"])


@router.get("/knowledge/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    response: Response,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    thread_id: Annotated[str | None, Query(max_length=120)] = None,
    context: RequestContext = Depends(require_permission("knowledge.search")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> KnowledgeSearchResponse:
    resolved_thread_id = thread_id or f"knowledge-{uuid4().hex}"
    result = await KnowledgeWorkflowService(session_factory).run(
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


__all__ = ["router"]
