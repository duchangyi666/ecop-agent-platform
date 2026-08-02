from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.database.base import TenantScope
from backend.database.unit_of_work import UnitOfWork


class KnowledgeSearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    scope: TenantScope
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=20)


class KnowledgeDocumentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: UUID
    title: str
    external_document_id: str
    source_uri: str | None
    status: str
    visibility: str
    content_snippet: str | None = None


class KnowledgeTool:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def search(
        self,
        request: KnowledgeSearchRequest,
    ) -> list[KnowledgeDocumentResult]:
        documents = await self.uow.knowledge.search_documents(
            scope=request.scope,
            query=request.query,
            limit=request.limit,
        )
        return [
            KnowledgeDocumentResult(
                document_id=document.id,
                title=document.title,
                external_document_id=document.external_document_id,
                source_uri=document.source_uri,
                status=document.status,
                visibility=document.visibility,
            )
            for document in documents
        ]


__all__ = [
    "KnowledgeDocumentResult",
    "KnowledgeSearchRequest",
    "KnowledgeTool",
]
