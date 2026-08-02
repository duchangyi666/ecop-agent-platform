from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

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
from backend.api.schemas import (
    KnowledgeDeleteResponse,
    KnowledgeDocumentListItem,
    KnowledgeDocumentListResponse,
    KnowledgeIngestResponse,
    KnowledgeReindexResponse,
    KnowledgeSearchResponse,
)
from backend.database.unit_of_work import UnitOfWork
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


@router.get("/knowledge/documents", response_model=KnowledgeDocumentListResponse)
async def list_knowledge_documents(
    context: RequestContext = Depends(require_permission("knowledge.search")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> KnowledgeDocumentListResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        documents = await uow.knowledge.list_documents(
            scope=context.scope,
            limit=limit,
            status="active",
        )
    return KnowledgeDocumentListResponse(
        request_id=context.request_id,
        documents=[
            KnowledgeDocumentListItem(
                document_id=document.id,
                external_document_id=document.external_document_id,
                title=document.title,
                status=document.status,
                source_uri=document.source_uri,
                visibility=document.visibility,
                created_at=document.created_at,
                updated_at=document.updated_at,
            )
            for document in documents
        ],
    )


@router.delete("/knowledge/documents/{document_id}", response_model=KnowledgeDeleteResponse)
async def delete_knowledge_document(
    document_id: UUID,
    context: RequestContext = Depends(require_permission("knowledge.delete")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
    vector_store: KnowledgeVectorStore | None = Depends(get_knowledge_vector_store),
) -> KnowledgeDeleteResponse:
    vector_indexed = False
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        document = await uow.knowledge.archive_document(
            scope=context.scope,
            document_id=document_id,
        )
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "document_not_found", "message": "document not found"},
            )
        await uow.support.append_audit_log(
            scope=context.scope,
            actor_id=context.scope.actor_id,
            action="knowledge.document_archived",
            resource_type="document",
            resource_id=document_id,
            metadata={"title": document.title, "external_document_id": document.external_document_id},
        )
    if vector_store is not None:
        await vector_store.delete_document_chunks(
            tenant_id=context.scope.tenant_id,
            document_id=document_id,
        )
        vector_indexed = True
    return KnowledgeDeleteResponse(
        request_id=context.request_id,
        document_id=document_id,
        status="archived",
        vector_indexed=vector_indexed,
    )


@router.post("/knowledge/reindex", response_model=KnowledgeReindexResponse)
async def reindex_knowledge_documents(
    context: RequestContext = Depends(require_permission("knowledge.ingest")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
    vector_store: KnowledgeVectorStore | None = Depends(get_knowledge_vector_store),
) -> KnowledgeReindexResponse:
    document_count = 0
    chunk_count = 0
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        documents = await uow.knowledge.list_documents(
            scope=context.scope,
            limit=500,
            status="active",
        )
        for document in documents:
            chunks = await uow.knowledge.list_document_chunks(
                scope=context.scope,
                document_id=document.id,
            )
            if not chunks:
                continue
            document_count += 1
            chunk_count += len(chunks)
            if vector_store is not None:
                await vector_store.upsert_document_chunks(
                    tenant_id=context.scope.tenant_id,
                    document=document,
                    chunks=chunks,
                )
    return KnowledgeReindexResponse(
        request_id=context.request_id,
        document_count=document_count,
        chunk_count=chunk_count,
        vector_indexed=vector_store is not None,
    )


__all__ = ["router"]
