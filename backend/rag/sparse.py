from __future__ import annotations

import hashlib
import math
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from backend.rag.config import RAGSettings


class SparseTextEmbedder(Protocol):
    def embed_sparse(self, texts: Sequence[str]) -> list[dict[int, float]]: ...


class DeterministicSparseEmbedder:
    def embed_sparse(self, texts: Sequence[str]) -> list[dict[int, float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> dict[int, float]:
        tokens = self._tokenize(text)
        counts = Counter(tokens)
        vector: dict[int, float] = {}
        for token, count in counts.items():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:6], "big") % 1_000_000
            vector[index] = math.sqrt(count)
        return vector

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        normalized = text.lower()
        return [part for part in normalized.replace("。", " ").replace("，", " ").split()]


class BgeM3SparseEmbedder:
    def __init__(self, model_path: str) -> None:
        resolved = Path(model_path).expanduser()
        if not resolved.is_dir():
            raise RuntimeError(f"BGE-M3 model path does not exist: {resolved}")
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:  # pragma: no cover - optional local model package
            raise RuntimeError("FlagEmbedding is required for BgeM3SparseEmbedder") from exc
        self._model = BGEM3FlagModel(
            str(resolved),
            use_fp16=False,
        )

    def embed_sparse(self, texts: Sequence[str]) -> list[dict[int, float]]:
        output = self._model.encode(
            list(texts),
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        return [
            {
                int(index): float(weight)
                for index, weight in lexical_weights.items()
            }
            for lexical_weights in output["lexical_weights"]
        ]


def create_sparse_embedder(settings: RAGSettings) -> SparseTextEmbedder | None:
    if not settings.sparse_vector_enabled:
        return None
    if settings.bge_m3_model_path:
        return BgeM3SparseEmbedder(settings.bge_m3_model_path)
    return DeterministicSparseEmbedder()


__all__ = [
    "BgeM3SparseEmbedder",
    "DeterministicSparseEmbedder",
    "SparseTextEmbedder",
    "create_sparse_embedder",
]
