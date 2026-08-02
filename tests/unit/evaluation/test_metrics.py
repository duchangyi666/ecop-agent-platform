from __future__ import annotations

from backend.evaluation.metrics import compute_retrieval_metrics


def test_retrieval_metrics_when_all_relevant_are_found() -> None:
    metrics = compute_retrieval_metrics(
        {"a", "b"},
        ["a", "x", "b"],
        k=3,
    )

    assert metrics["recall_at_k"] == 1.0
    assert metrics["precision_at_k"] == 2 / 3
    assert metrics["mrr"] == 1.0
    assert 0.9 < metrics["ndcg_at_k"] < 1.0


def test_retrieval_metrics_handles_missed_first_rank() -> None:
    metrics = compute_retrieval_metrics(
        {"a"},
        ["x", "a"],
        k=2,
    )

    assert metrics["recall_at_k"] == 1.0
    assert metrics["mrr"] == 0.5
    assert 0.0 < metrics["ndcg_at_k"] < 1.0


def test_retrieval_metrics_empty_relevant_returns_zero() -> None:
    metrics = compute_retrieval_metrics(set(), ["a"], k=1)

    assert metrics["recall_at_k"] == 0.0
    assert metrics["mrr"] == 0.0
    assert metrics["ndcg_at_k"] == 0.0
