from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database.models.governance import Document
from backend.database.models.knowledge import KnowledgeChunk
from backend.rag.bge_hybrid import BgeM3HybridEmbedder
from backend.rag.vector_store import MilvusKnowledgeVectorStore


async def verify_bge_m3(*, model_path: str, milvus_uri: str) -> dict:
    embedder = BgeM3HybridEmbedder(model_path)
    dense = embedder.embed(["同一账单在二十四小时内重复扣费可以申请退款。"])
    sparse = embedder.embed_sparse(["同一账单在二十四小时内重复扣费可以申请退款。"])

    tenant_id = uuid4()
    document_id = uuid4()
    chunk_id = uuid4()
    document = Document(
        id=document_id,
        tenant_id=tenant_id,
        external_document_id="bge-real",
        title="退款政策",
        status="active",
        source_uri="https://docs.example.com/bge-real",
        visibility="tenant",
    )
    chunk = KnowledgeChunk(
        id=chunk_id,
        tenant_id=tenant_id,
        document_id=document_id,
        chunk_number=1,
        content="同一账单在二十四小时内重复扣费可以申请退款。",
        content_hash="hash",
        token_count=20,
        status="active",
    )
    collection = f"ecop_verify_bge_{uuid4().hex[:8]}"
    store = MilvusKnowledgeVectorStore(
        uri=milvus_uri,
        collection_name=collection,
        embedder=embedder,
        sparse_embedder=embedder,
    )
    try:
        await store.upsert_document_chunks(
            tenant_id=tenant_id,
            document=document,
            chunks=[chunk],
        )
        hits = await store.search(
            tenant_id=tenant_id,
            query="重复扣费退款政策",
            limit=5,
        )
        return {
            "dimension": embedder.dimension,
            "dense_dimension": len(dense[0]),
            "sparse_keys": len(sparse[0]),
            "hit_count": len(hits),
            "hit_title": hits[0].title if hits else None,
        }
    finally:
        await store.drop_collection()
        await store.close()


def _parse_args() -> argparse.Namespace:
    default_model = (
        PROJECT_ROOT / "models" / "bge-m3"
    )
    parser = argparse.ArgumentParser(description="Verify local BGE-M3 dense and sparse retrieval.")
    parser.add_argument(
        "--model-path",
        default=os.getenv("BGE_M3_MODEL_PATH", str(default_model)),
    )
    parser.add_argument(
        "--milvus-uri",
        default=os.getenv("MILVUS_URI", "http://localhost:19531"),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = asyncio.run(
        verify_bge_m3(
            model_path=args.model_path,
            milvus_uri=args.milvus_uri,
        )
    )
    print(result)


if __name__ == "__main__":
    main()
