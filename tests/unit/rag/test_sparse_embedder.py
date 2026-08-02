from __future__ import annotations

from backend.rag.sparse import DeterministicSparseEmbedder


def test_deterministic_sparse_embedder_returns_token_vectors() -> None:
    first = DeterministicSparseEmbedder().embed_sparse(["退款 政策"])
    second = DeterministicSparseEmbedder().embed_sparse(["退款 政策"])

    assert first[0]
    assert first == second
    assert all(value > 0 for value in first[0].values())
