from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.guards import InputSecurityGuard
from backend.database.base import TenantScope
from backend.database.models.governance import DocumentVersion
from backend.database.models.knowledge import KnowledgeChunk
from backend.database.unit_of_work import UnitOfWork
from backend.domain.common import DomainError
from backend.rag.text_splitter import split_knowledge_text
from backend.rag.vector_store import KnowledgeVectorStore


class KnowledgeIngestRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    thread_id: str = Field(min_length=1, max_length=120)
    external_document_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=255)
    source_uri: str | None = Field(default=None, max_length=500)
    visibility: Literal["tenant", "public"] = "tenant"
    content: str = Field(min_length=1, max_length=200000)
    chunk_size: int = Field(default=800, ge=100, le=4000)
    chunk_overlap: int = Field(default=80, ge=0, le=500)


@dataclass(frozen=True, slots=True)
class KnowledgeIngestResult:
    thread_id: str
    document_id: UUID
    version_number: int
    chunk_count: int
    vector_indexed: bool
    trace_id: UUID | None = None
    audit_event_ids: list[UUID] = field(default_factory=list)


class KnowledgeIngestService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        vector_store: KnowledgeVectorStore | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.vector_store = vector_store

    async def run(
        self,
        *,
        scope: TenantScope,
        request: KnowledgeIngestRequest,
    ) -> KnowledgeIngestResult:
        guard = InputSecurityGuard().evaluate(f"{request.title}\n{request.content}")
        if guard.status != "allow":
            raise DomainError("知识内容未通过安全审查，已阻止摄取。")

        overlap = min(request.chunk_overlap, request.chunk_size // 2)
        chunk_texts = split_knowledge_text(
            request.content,
            chunk_size=request.chunk_size,
            chunk_overlap=overlap,
        )
        if not chunk_texts:
            raise DomainError("知识内容为空，无法摄取。")

        content_hash = hashlib.sha256(request.content.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)

        async with UnitOfWork(self.session_factory, scope=scope) as uow:
            trace = await uow.governance.create_runtime_trace(
                scope=scope,
                trace_key=f"{request.thread_id}-{request.external_document_id}",
                entrypoint="agent.knowledge.ingest",
                input_summary="knowledge document ingest",
                input_hash=hashlib.sha256(
                    f"{request.thread_id}:{request.external_document_id}".encode("utf-8")
                ).hexdigest(),
            )
            document = await uow.knowledge.upsert_document(
                scope=scope,
                external_document_id=request.external_document_id,
                title=request.title,
                source_uri=request.source_uri,
                visibility=request.visibility,
            )
            version_number = await uow.knowledge.next_document_version_number(
                scope=scope,
                document_id=document.id,
            )
            uow.session.add(
                DocumentVersion(
                    id=uuid4(),
                    tenant_id=scope.tenant_id,
                    document_id=document.id,
                    version_number=version_number,
                    content_hash=content_hash,
                    object_uri=request.source_uri or f"memory://{request.external_document_id}",
                    effective_from=now,
                    effective_to=None,
                    chunk_count=len(chunk_texts),
                )
            )
            chunks = [
                KnowledgeChunk(
                    id=uuid4(),
                    tenant_id=scope.tenant_id,
                    document_id=document.id,
                    chunk_number=index,
                    content=text,
                    content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    token_count=len(text),
                    status="active",
                )
                for index, text in enumerate(chunk_texts, start=1)
            ]
            stored_chunks = await uow.knowledge.replace_document_chunks(
                scope=scope,
                document_id=document.id,
                chunks=chunks,
            )

            vector_indexed = False
            if self.vector_store is not None:
                await self.vector_store.upsert_document_chunks(
                    tenant_id=scope.tenant_id,
                    document=document,
                    chunks=stored_chunks,
                )
                vector_indexed = True

            audit = await uow.support.append_audit_log(
                scope=scope,
                actor_id=scope.actor_id,
                action="knowledge_ingested",
                resource_type="knowledge",
                resource_id=document.id,
                metadata={
                    "thread_id": request.thread_id,
                    "external_document_id": request.external_document_id,
                    "version_number": version_number,
                    "chunk_count": len(stored_chunks),
                    "vector_indexed": vector_indexed,
                },
            )
            await uow.governance.complete_runtime_trace(
                trace_id=trace.id,
                status="completed",
                error_summary=None,
            )

        return KnowledgeIngestResult(
            thread_id=request.thread_id,
            document_id=document.id,
            version_number=version_number,
            chunk_count=len(stored_chunks),
            vector_indexed=vector_indexed,
            trace_id=trace.id,
            audit_event_ids=[audit.id],
        )


__all__ = ["KnowledgeIngestRequest", "KnowledgeIngestResult", "KnowledgeIngestService"]
