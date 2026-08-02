from __future__ import annotations

from backend.llm.context import estimate_tokens, truncate_text


def test_truncate_text_keeps_short_text() -> None:
    assert truncate_text("short", 10) == "short"


def test_truncate_text_limits_long_text() -> None:
    result = truncate_text("a" * 100, 10)

    assert len(result) <= 10
    assert result.endswith("...")


def test_estimate_tokens_returns_positive_value() -> None:
    assert estimate_tokens("中文客户服务提示词") > 0
