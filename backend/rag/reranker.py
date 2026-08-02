from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from backend.agent.state import KnowledgeEvidence
from backend.agent.tools.knowledge import KnowledgeDocumentResult
from backend.rag.config import RAGSettings


class KnowledgeReranker(Protocol):
    async def rerank(
        self,
        *,
        query: str,
        candidates: list[KnowledgeEvidence],
    ) -> list[KnowledgeEvidence]: ...


class DeterministicReranker:
    async def rerank(
        self,
        *,
        query: str,
        candidates: list[KnowledgeEvidence],
    ) -> list[KnowledgeEvidence]:
        del query
        return sorted(
            candidates,
            key=lambda item: (item.score if item.score is not None else 0.0),
            reverse=True,
        )


class CrossEncoderReranker:
    def __init__(self, model_path: str) -> None:
        resolved = Path(model_path).expanduser()
        if not resolved.is_dir():
            raise RuntimeError(f"reranker model path does not exist: {resolved}")
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - optional local model package
            raise RuntimeError("sentence-transformers is required for CrossEncoderReranker") from exc
        self._model = CrossEncoder(str(resolved))

    async def rerank(
        self,
        *,
        query: str,
        candidates: list[KnowledgeEvidence],
    ) -> list[KnowledgeEvidence]:
        if not candidates:
            return []
        pairs = [
            (query, item.content_snippet or item.title)
            for item in candidates
        ]
        scores = await asyncio.to_thread(self._model.predict, pairs)
        ranked = sorted(
            zip(candidates, [float(score) for score in scores]),
            key=lambda pair: pair[1],
            reverse=True,
        )
        return [
            item.model_copy(update={"score": score})
            for item, score in ranked
        ]


class KnowledgeDocumentReranker(Protocol):
    async def rerank(
        self,
        *,
        query: str,
        candidates: list[KnowledgeDocumentResult],
    ) -> list[KnowledgeDocumentResult]: ...


class DeterministicDocumentReranker:
    async def rerank(
        self,
        *,
        query: str,
        candidates: list[KnowledgeDocumentResult],
    ) -> list[KnowledgeDocumentResult]:
        del query
        return sorted(
            candidates,
            key=lambda item: (item.score if item.score is not None else 0.0),
            reverse=True,
        )


class CrossEncoderDocumentReranker:
    def __init__(self, model_path: str) -> None:
        resolved = Path(model_path).expanduser()
        if not resolved.is_dir():
            raise RuntimeError(f"reranker model path does not exist: {resolved}")
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - optional local model package
            raise RuntimeError("sentence-transformers is required for CrossEncoderDocumentReranker") from exc
        self._model = CrossEncoder(str(resolved))

    async def rerank(
        self,
        *,
        query: str,
        candidates: list[KnowledgeDocumentResult],
    ) -> list[KnowledgeDocumentResult]:
        if not candidates:
            return []
        pairs = [
            (query, item.content_snippet or item.title)
            for item in candidates
        ]
        scores = await asyncio.to_thread(self._model.predict, pairs)
        ranked = sorted(
            zip(candidates, [float(score) for score in scores]),
            key=lambda pair: pair[1],
            reverse=True,
        )
        return [
            item.model_copy(update={"score": score})
            for item, score in ranked
        ]


def create_reranker(settings: RAGSettings) -> KnowledgeReranker:
    if settings.reranker_model_path:
        return CrossEncoderReranker(settings.reranker_model_path)
    return DeterministicReranker()


def create_document_reranker(settings: RAGSettings) -> KnowledgeDocumentReranker:
    if settings.reranker_model_path:
        return CrossEncoderDocumentReranker(settings.reranker_model_path)
    return DeterministicDocumentReranker()


__all__ = [
    "CrossEncoderReranker",
    "CrossEncoderDocumentReranker",
    "DeterministicDocumentReranker",
    "DeterministicReranker",
    "KnowledgeDocumentReranker",
    "KnowledgeReranker",
    "create_document_reranker",
    "create_reranker",
]
