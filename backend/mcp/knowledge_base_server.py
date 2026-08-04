"""MCP server exposing CloudDesk knowledge retrieval as a tool.

Mounted in-process at ``/mcp/kb``; agents (or external MCP clients) call
``search_knowledge`` over JSON-RPC. Degrades to ``[]`` when the vector store or
DB is unavailable so it never blocks a conversation.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="CloudDesk-KnowledgeBase",
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
async def search_knowledge(query: str, tenant_id: str, top_k: int = 3) -> list[dict]:
    """Hybrid semantic + keyword search over the tenant knowledge base.

    Returns the top-``top_k`` relevant chunks with title/snippet/score.
    """
    from backend.database.base import TenantScope
    from backend.database.session import get_session_factory
    from backend.rag.config import get_rag_settings
    from backend.rag.reranker import create_reranker
    from backend.rag.retriever import ConsultationKnowledgeRetriever
    from backend.rag.vector_store import create_knowledge_vector_store

    try:
        scope = TenantScope(tenant_id=UUID(tenant_id))
        retriever = ConsultationKnowledgeRetriever(
            get_session_factory(),
            vector_store=create_knowledge_vector_store(),
            reranker=create_reranker(get_rag_settings()),
        )
        evidence = await retriever.retrieve(scope=scope, query=query, limit=top_k)
        return [
            {
                "document_id": str(item.document_id),
                "title": item.title,
                "snippet": item.content_snippet or "",
                "score": item.score,
            }
            for item in evidence
        ]
    except Exception:  # noqa: BLE001 - silent degrade, never block the caller
        return []


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=8003)
