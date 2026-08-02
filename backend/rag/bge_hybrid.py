from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


class BgeM3HybridEmbedder:
    """Single BGE-M3 model used for both dense and sparse Milvus vectors."""

    def __init__(self, model_path: str) -> None:
        resolved = Path(model_path).expanduser()
        if not resolved.is_dir():
            raise RuntimeError(f"BGE-M3 model path does not exist: {resolved}")
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:  # pragma: no cover - local model dependency
            raise RuntimeError("FlagEmbedding is required for BgeM3HybridEmbedder") from exc
        self._model = BGEM3FlagModel(
            str(resolved),
            use_fp16=False,
        )
        self.dimension = int(self._model.model.config.hidden_size)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        output = self._model.encode(
            list(texts),
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return [list(map(float, vector)) for vector in output["dense_vecs"]]

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


__all__ = ["BgeM3HybridEmbedder"]
