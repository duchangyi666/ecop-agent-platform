"""Index synthetic knowledge documents into Milvus so RAG retrieval works.

Reads all active Documents + KnowledgeChunks from PostgreSQL and upserts
them (BGE-M3 dense + sparse vectors) into the configured Milvus collection.
Requires MILVUS_URI, BGE_M3_MODEL_PATH and SPARSE_VECTOR_ENABLED=1.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.config import get_settings
from backend.database.models.governance import Document
from backend.database.models.knowledge import KnowledgeChunk
from backend.rag.config import get_rag_settings
from backend.rag.vector_store import create_knowledge_vector_store


async def index_all(*, database_url: str, tenant_id: str | None = None) -> dict:
    rag = get_rag_settings()
    store = create_knowledge_vector_store(rag)
    if store is None:
        raise RuntimeError("vector store not configured (set MILVUS_URI and BGE_M3_MODEL_PATH)")

    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    total_docs = 0
    total_chunks = 0
    try:
        async with session_factory() as session:
            statement = select(Document).where(
                Document.deleted_at.is_(None),
                Document.status == "active",
            )
            if tenant_id:
                from uuid import UUID

                statement = statement.where(Document.tenant_id == UUID(tenant_id))
            documents = list((await session.scalars(statement)).all())
            for index, document in enumerate(documents, start=1):
                chunks = list(
                    (
                        await session.scalars(
                            select(KnowledgeChunk).where(
                                KnowledgeChunk.document_id == document.id,
                                KnowledgeChunk.status == "active",
                            )
                        )
                    ).all()
                )
                if not chunks:
                    continue
                await store.upsert_document_chunks(
                    tenant_id=document.tenant_id,
                    document=document,
                    chunks=chunks,
                )
                total_docs += 1
                total_chunks += len(chunks)
                if index % 50 == 0:
                    print(f"  indexed {index}/{len(documents)} documents")
    finally:
        await store.close()
        await engine.dispose()
    return {"documents": total_docs, "chunks": total_chunks}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index synthetic knowledge into Milvus.")
    parser.add_argument("--tenant-id", default=os.getenv("INDEX_TENANT_ID"), help="optional tenant UUID to scope")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", get_settings().database_url))
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = asyncio.run(index_all(database_url=args.database_url, tenant_id=args.tenant_id))
    print(f"indexed {result['documents']} documents / {result['chunks']} chunks into Milvus")
