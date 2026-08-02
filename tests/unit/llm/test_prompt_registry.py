from __future__ import annotations

import pytest

from backend.llm.prompt_registry import (
    PromptRecord,
    PromptRegistry,
    create_default_prompt_registry,
)


def test_prompt_registry_returns_latest_published_version() -> None:
    registry = PromptRegistry(
        [
            PromptRecord(
                code="customer_service",
                version="v1",
                template="v1",
                status="deprecated",
            ),
            PromptRecord(
                code="customer_service",
                version="v2",
                template="v2",
                status="published",
            ),
        ]
    )

    assert registry.get("customer_service").version == "v2"


def test_default_prompt_registry_contains_customer_service() -> None:
    registry = create_default_prompt_registry()

    record = registry.get("customer_service")

    assert "CloudDesk" in record.template


def test_prompt_registry_rejects_missing_prompt() -> None:
    with pytest.raises(KeyError):
        PromptRegistry().get("missing")
