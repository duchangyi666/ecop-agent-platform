from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from backend.rag.config import RAGSettings


@runtime_checkable
class TextEmbedder(Protocol):
    dimension: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class DeterministicEmbedder:
    def __init__(self, dimension: int = 384) -> None:
        if dimension < 16:
            raise ValueError("embedding dimension must be at least 16")
        self.dimension = dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        normalized = " ".join(text.lower().split())
        if not normalized:
            return vector

        counts: dict[str, int] = {}
        for character in normalized:
            counts[character] = counts.get(character, 0) + 1

        for character, count in counts.items():
            digest = hashlib.blake2b(character.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign * math.sqrt(count)

        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector


class BgeM3Embedder:
    def __init__(self, model_path: str) -> None:
        resolved = Path(model_path).expanduser()
        if not resolved.is_dir():
            raise RuntimeError(f"BGE-M3 model path does not exist: {resolved}")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on optional local package
            raise RuntimeError("sentence-transformers is required for BgeM3Embedder") from exc

        self._model = SentenceTransformer(str(resolved))
        self.dimension = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=8,
        )
        return [list(map(float, vector)) for vector in vectors]


def create_embedder(settings: RAGSettings) -> TextEmbedder:
    if settings.bge_m3_model_path:
        return BgeM3Embedder(settings.bge_m3_model_path)
    return DeterministicEmbedder(settings.embedding_dim)


__all__ = ["BgeM3Embedder", "DeterministicEmbedder", "TextEmbedder", "create_embedder"]
