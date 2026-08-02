from __future__ import annotations

from typing import Any
from uuid import UUID

from backend.agent.state import KnowledgeEvidence
from backend.agent.tools.knowledge import KnowledgeDocumentResult


def _rrf_score(ranks: list[int]) -> float:
    return sum(1.0 / (60 + rank) for rank in ranks)


def merge_evidence(
    vector_evidence: list[KnowledgeEvidence],
    postgres_evidence: list[KnowledgeEvidence],
    *,
    limit: int,
) -> list[KnowledgeEvidence]:
    entries: dict[UUID, dict[str, Any]] = {}
    for items in (vector_evidence, postgres_evidence):
        for rank, item in enumerate(items, start=1):
            entry = entries.setdefault(
                item.document_id,
                {"ranks": [], "best": item},
            )
            entry["ranks"].append(rank)
            best = entry["best"]
            if item.content_snippet and (
                best.content_snippet is None or item.score is not None
            ):
                entry["best"] = item

    merged: list[KnowledgeEvidence] = []
    for entry in entries.values():
        best = entry["best"]
        ranks = entry["ranks"]
        merged.append(
            best.model_copy(
                update={"score": _rrf_score(ranks)}
            )
        )
    merged.sort(key=lambda item: (-(item.score or 0.0), item.title))
    return merged[:limit]


def merge_document_results(
    vector_results: list[KnowledgeDocumentResult],
    postgres_results: list[KnowledgeDocumentResult],
    *,
    limit: int,
) -> list[KnowledgeDocumentResult]:
    entries: dict[UUID, dict[str, Any]] = {}
    for items in (vector_results, postgres_results):
        for rank, item in enumerate(items, start=1):
            entry = entries.setdefault(
                item.document_id,
                {"ranks": [], "best": item},
            )
            entry["ranks"].append(rank)
            best = entry["best"]
            if item.content_snippet and best.content_snippet is None:
                entry["best"] = item

    merged: list[KnowledgeDocumentResult] = []
    for entry in entries.values():
        best = entry["best"]
        ranks = entry["ranks"]
        merged.append(
            best.model_copy(
                update={"score": _rrf_score(ranks)}
            )
        )
    merged.sort(key=lambda item: (-(item.score or 0.0), item.title))
    return merged[:limit]


__all__ = ["merge_document_results", "merge_evidence"]
