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


def test_negated_preferences_are_not_captured():
    extractor = DeterministicMemoryExtractor()
    for message in (
        "不要使用中文", "不希望使用邮件通知", "不要记住我喜欢邮件通知",
        "I do not prefer email", "我的时区不是时区是 Asia/Shanghai",
    ):
        assert extractor.extract(message=message) == [], message


def test_language_switch_keeps_only_affirmative_new_choice():
    candidates = DeterministicMemoryExtractor().extract(message="不要使用中文，改为使用英文")
    assert [(item.memory_type, item.content) for item in candidates] == [
        ("language_preference", "preferred_language=en"),
    ]


def test_timezone_uses_latest_affirmative_clause():
    candidates = DeterministicMemoryExtractor().extract(
        message="时区是 Asia/Shanghai；现在时区是 Europe/London",
    )
    assert candidates[0].content == "timezone=Europe/London"


def test_language_codes_require_complete_values():
    extractor = DeterministicMemoryExtractor()
    for text in ("language=english", "language=zh-invalid", "mylanguage=en", "language=en_US"):
        assert extractor.extract(message=text) == [], text
    for text, expected in (("language=en", "preferred_language=en"),
                           ("language=zh-cn", "preferred_language=zh")):
        assert extractor.extract(message=text)[0].content == expected


def test_timezone_must_exist_in_timezone_database():
    extractor = DeterministicMemoryExtractor()
    for text in ("时区是 Not/AZone", "timezone=../invalid", "时区为 Mars/Olympus"):
        assert extractor.extract(message=text) == [], text
    assert extractor.extract(message="时区是 Asia/Shanghai")[0].content == "timezone=Asia/Shanghai"
