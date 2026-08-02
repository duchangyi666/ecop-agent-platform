from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    memory_type: str
    content: str
    confidence: float
    ttl_days: int
    source: str = "conversation"


class DeterministicMemoryExtractor:
    _preference_patterns = (
        "我偏好",
        "我喜欢",
        "我们偏好",
        "希望使用",
        "prefer",
        "偏好使用",
    )
    _language_markers = (
        "使用中文",
        "中文沟通",
        "工作语言是中文",
        "language=zh",
        "language=zh-cn",
    )
    _timezone_pattern = re.compile(r"(?:时区是|时区为|timezone[=:])\s*([\w/+:-]+)")

    def extract(
        self,
        *,
        message: str,
        response: str | None = None,
    ) -> list[MemoryCandidate]:
        del response
        text = message or ""
        candidates: list[MemoryCandidate] = []
        normalized = text.lower()

        for marker in self._language_markers:
            if marker in normalized:
                candidates.append(
                    MemoryCandidate(
                        memory_type="language_preference",
                        content="preferred_language=zh",
                        confidence=0.9,
                        ttl_days=365,
                    )
                )
                break

        timezone_match = self._timezone_pattern.search(text)
        if timezone_match:
            candidates.append(
                MemoryCandidate(
                    memory_type="timezone_preference",
                    content=f"timezone={timezone_match.group(1).strip()[:80]}",
                    confidence=0.8,
                    ttl_days=365,
                )
            )

        for marker in self._preference_patterns:
            if marker in normalized:
                content = self._extract_after(text, marker)
                if content:
                    candidates.append(
                        MemoryCandidate(
                            memory_type="user_preference",
                            content=f"preference={content[:200]}",
                            confidence=0.8,
                            ttl_days=90,
                        )
                    )
                break

        return candidates

    @staticmethod
    def _extract_after(text: str, marker: str) -> str:
        index = text.lower().find(marker)
        if index < 0:
            return ""
        remainder = text[index + len(marker) :].strip(" ，,。.;；")
        return re.sub(r"\s+", " ", remainder)[:200]


__all__ = ["DeterministicMemoryExtractor", "MemoryCandidate"]
