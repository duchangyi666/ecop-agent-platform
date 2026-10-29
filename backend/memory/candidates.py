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

        language_matches = [
            (normalized.rfind(marker), language)
            for language, markers in (
                ("zh", self._language_markers),
                ("en", ("使用英文", "英文沟通", "工作语言是英文", "language=en")),
            )
            for marker in markers if marker in normalized
            and self._is_affirmative(normalized, normalized.rfind(marker))
        ]
        if language_matches:
            _, language = max(language_matches)
            candidates.append(MemoryCandidate(
                memory_type="language_preference", content=f"preferred_language={language}",
                confidence=0.9, ttl_days=365,
            ))

        timezone_match = next((match for match in reversed(list(self._timezone_pattern.finditer(text)))
                               if self._is_affirmative(normalized, match.start())), None)
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
            if marker in normalized and self._is_affirmative(normalized, normalized.find(marker)):
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
    def _is_affirmative(text: str, index: int) -> bool:
        # Be conservative: negation in the same clause must not become a preference.
        prefix = re.split(r"[，,。.;；!?！？\n]", text[:index])[-1]
        return re.search(
            r"不|不要|别|禁止|勿|取消|撤销|并非|不是|\b(?:not|never|don['’]t|do not)\b",
            prefix, re.IGNORECASE,
        ) is None

    @staticmethod
    def _extract_after(text: str, marker: str) -> str:
        index = text.lower().find(marker)
        if index < 0:
            return ""
        remainder = text[index + len(marker) :].strip(" ，,。.;；")
        return re.sub(r"\s+", " ", remainder)[:200]


__all__ = ["DeterministicMemoryExtractor", "MemoryCandidate"]
