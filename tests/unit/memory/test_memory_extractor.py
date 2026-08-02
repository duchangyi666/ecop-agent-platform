from __future__ import annotations

from backend.memory.candidates import DeterministicMemoryExtractor


def test_extractor_finds_language_and_preference_candidates() -> None:
    candidates = DeterministicMemoryExtractor().extract(
        message="客户咨询，我偏好使用中文沟通",
    )

    types = {candidate.memory_type for candidate in candidates}
    assert "language_preference" in types
    assert "user_preference" in types
    assert all(candidate.confidence >= 0.8 for candidate in candidates)


def test_extractor_ignores_message_without_memory_marker() -> None:
    candidates = DeterministicMemoryExtractor().extract(
        message="我的账单金额有问题",
    )

    assert candidates == []
