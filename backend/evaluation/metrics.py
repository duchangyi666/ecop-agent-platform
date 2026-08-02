from __future__ import annotations

import math
from collections.abc import Sequence


def recall_at_k(
    relevant: set[str],
    retrieved: Sequence[str],
    *,
    k: int,
) -> float:
    if not relevant:
        return 0.0
    hits = sum(1 for item in retrieved[:k] if item in relevant)
    return min(1.0, hits / len(relevant))


def precision_at_k(
    relevant: set[str],
    retrieved: Sequence[str],
    *,
    k: int,
) -> float:
    if k <= 0:
        return 0.0
    hits = sum(1 for item in retrieved[:k] if item in relevant)
    return hits / min(k, max(1, len(retrieved[:k])))


def reciprocal_rank(
    relevant: set[str],
    retrieved: Sequence[str],
) -> float:
    for index, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def ndcg_at_k(
    relevant: set[str],
    retrieved: Sequence[str],
    *,
    k: int,
) -> float:
    def dcg(items: Sequence[str]) -> float:
        return sum(
            1.0 / math.log2(index + 2)
            for index, item in enumerate(items[:k])
            if item in relevant
        )

    ideal_count = min(len(relevant), k)
    ideal = [1.0] * ideal_count
    denominator = sum(value / math.log2(index + 2) for index, value in enumerate(ideal))
    if denominator == 0:
        return 0.0
    return dcg(retrieved) / denominator


def compute_retrieval_metrics(
    relevant: set[str],
    retrieved: Sequence[str],
    *,
    k: int,
) -> dict[str, float]:
    return {
        "recall_at_k": recall_at_k(relevant, retrieved, k=k),
        "precision_at_k": precision_at_k(relevant, retrieved, k=k),
        "mrr": reciprocal_rank(relevant, retrieved),
        "ndcg_at_k": ndcg_at_k(relevant, retrieved, k=k),
    }


__all__ = [
    "compute_retrieval_metrics",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
]
