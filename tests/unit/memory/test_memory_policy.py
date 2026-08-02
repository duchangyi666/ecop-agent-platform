from __future__ import annotations

from backend.memory.candidates import MemoryCandidate
from backend.memory.policy import MemoryWritePolicy


def test_memory_policy_allows_stable_preference() -> None:
    candidate = MemoryCandidate(
        memory_type="user_preference",
        content="preference=中文沟通",
        confidence=0.8,
        ttl_days=90,
    )

    assert MemoryWritePolicy().allow(candidate) is True


def test_memory_policy_rejects_credential_and_transient_content() -> None:
    policy = MemoryWritePolicy()

    assert (
        policy.allow(
            MemoryCandidate(
                memory_type="user_preference",
                content="preference=token sk-test-123456789",
                confidence=0.9,
                ttl_days=90,
            )
        )
        is False
    )
    assert (
        policy.allow(
            MemoryCandidate(
                memory_type="user_preference",
                content="preference=临时故障稍后再试",
                confidence=0.9,
                ttl_days=90,
            )
        )
        is False
    )
