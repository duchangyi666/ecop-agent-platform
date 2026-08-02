from __future__ import annotations

import re

from backend.memory.candidates import MemoryCandidate


class MemoryWritePolicy:
    _credential_patterns = (
        re.compile(r"\bsk-[a-z0-9][a-z0-9_-]{7,}\b"),
        re.compile(r"(?:api[\s_-]?key|password|passwd|secret|token)\s*[:=]\s*\S+"),
        re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
    )
    _transient_fragments = (
        "临时",
        "故障",
        "稍后",
        "待定",
        "不确定",
        "暂时",
    )
    max_content_length = 500
    min_confidence = 0.7

    def allow(self, candidate: MemoryCandidate) -> bool:
        content = candidate.content.strip()
        if not content:
            return False
        if len(content) > self.max_content_length:
            return False
        if candidate.confidence < self.min_confidence:
            return False
        normalized = content.casefold()
        if any(pattern.search(normalized) for pattern in self._credential_patterns):
            return False
        if any(fragment in content for fragment in self._transient_fragments):
            return False
        return True


__all__ = ["MemoryWritePolicy"]
