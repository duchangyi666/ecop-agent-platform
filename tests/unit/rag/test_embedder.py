from __future__ import annotations

import math

from backend.rag.embedder import DeterministicEmbedder


def test_deterministic_embedder_returns_stable_normalized_vectors() -> None:
    embedder = DeterministicEmbedder(dimension=32)

    first = embedder.embed(["重复扣费退款"])
    second = embedder.embed(["重复扣费退款"])

    assert len(first[0]) == 32
    assert first == second
    norm = math.sqrt(sum(value * value for value in first[0]))
    assert math.isclose(norm, 1.0, rel_tol=1e-6)
