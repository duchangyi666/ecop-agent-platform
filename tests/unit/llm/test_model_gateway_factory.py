from __future__ import annotations

import pytest

from backend.llm.config import ModelGatewaySettings
from backend.llm.deepseek import DeepSeekGateway
from backend.llm.fake import FakeModelGateway
from backend.llm.factory import create_model_gateway


def test_create_model_gateway_without_key_returns_fake() -> None:
    gateway = create_model_gateway(
        ModelGatewaySettings(
            api_key=None,
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
        )
    )

    assert isinstance(gateway, FakeModelGateway)


def test_create_model_gateway_with_key_returns_deepseek() -> None:
    gateway = create_model_gateway(
        ModelGatewaySettings(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
        )
    )

    assert isinstance(gateway, DeepSeekGateway)
    assert "test-key" not in repr(gateway.settings)


def test_create_model_gateway_defaults_to_fake_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    gateway = create_model_gateway()

    assert isinstance(gateway, FakeModelGateway)


def test_create_model_gateway_uses_deepseek_when_env_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-environment-key")

    gateway = create_model_gateway()

    assert isinstance(gateway, DeepSeekGateway)
    assert "test-environment-key" not in repr(gateway.settings)
