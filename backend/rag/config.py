from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field


class RAGSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    milvus_uri: str = Field(default="")
    milvus_collection: str = Field(default="ecop_knowledge_chunks_v2")
    embedding_dim: int = Field(default=384, ge=16, le=4096)
    bge_m3_model_path: str | None = Field(default=None)
    reranker_model_path: str | None = Field(default=None)
    sparse_vector_enabled: bool = Field(default=False)
    milvus_timeout: float = Field(default=10.0, gt=0.0)


@lru_cache(maxsize=1)
def get_rag_settings() -> RAGSettings:
    return RAGSettings(
        milvus_uri=os.getenv("MILVUS_URI", "").strip(),
        milvus_collection=os.getenv("MILVUS_COLLECTION", "ecop_knowledge_chunks_v2"),
        embedding_dim=int(os.getenv("EMBEDDING_DIM", "384")),
        bge_m3_model_path=os.getenv("BGE_M3_MODEL_PATH") or None,
        reranker_model_path=os.getenv("RERANKER_MODEL_PATH") or None,
        sparse_vector_enabled=os.getenv("SPARSE_VECTOR_ENABLED", "0").strip().lower()
        in {"1", "true", "yes", "on"},
        milvus_timeout=float(os.getenv("MILVUS_TIMEOUT", "10.0")),
    )


__all__ = ["RAGSettings", "get_rag_settings"]
