from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContextBudget:
    max_system_characters: int = 6000
    max_evidence_characters: int = 4000


def estimate_tokens(text: str) -> int:
    # Rough local estimate for mixed Chinese/English prompts; no external tokenizer.
    return max(1, len(text) // 2)


def truncate_text(text: str, max_characters: int) -> str:
    if max_characters <= 0:
        return ""
    if len(text) <= max_characters:
        return text
    return text[: max_characters - 3].rstrip() + "..."


__all__ = ["ContextBudget", "estimate_tokens", "truncate_text"]
