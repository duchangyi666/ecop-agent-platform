from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.agent.state import create_agent_state
from backend.database.base import TenantScope
from backend.llm.config import ModelGatewaySettings
from backend.llm.contracts import ModelCallError, ResponseDraft


def test_missing_api_key_is_optional_and_not_exposed_in_repr() -> None:
    settings = ModelGatewaySettings(
        api_key=None,
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )

    assert settings.api_key is None
    assert "None" in repr(settings.api_key)


def test_settings_read_key_from_environment_without_plaintext_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-environment-key")

    settings = ModelGatewaySettings.from_env()

    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "test-environment-key"
    assert "test-environment-key" not in repr(settings)


def test_response_draft_rejects_unknown_next_action() -> None:
    with pytest.raises(ValidationError):
        ResponseDraft(answer="ok", next_action="execute_refund", confidence=0.5)


def test_model_error_only_contains_safe_fields() -> None:
    error = ModelCallError(
        code="model_timeout",
        retryable=True,
        safe_message="模型服务暂时不可用",
    )

    serialized = error.model_dump_json()
    assert "Authorization" not in serialized
    assert "sk-" not in serialized


def test_agent_state_has_model_result_defaults() -> None:
    state = create_agent_state(
        scope=TenantScope(tenant_id=uuid4()),
        request_id=uuid4(),
        message="你好",
    )

    assert state.response_draft is None
    assert state.final_response is None
    assert state.model_usage is None
    assert state.model_error is None
    assert state.model_call_count == 0
    assert state.total_input_tokens == 0
    assert state.total_output_tokens == 0
