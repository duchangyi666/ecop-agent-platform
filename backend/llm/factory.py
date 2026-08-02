from __future__ import annotations

from backend.llm.config import ModelGatewaySettings
from backend.llm.contracts import ResponseDraft
from backend.llm.deepseek import DeepSeekGateway
from backend.llm.fake import FakeModelGateway
from backend.llm.gateway import ModelGateway

_DEFAULT_OFFLINE_RESPONSE = (
    "您好，我可以协助处理 CloudDesk 账户、账单、产品支持和工单问题。"
    "请描述您需要办理的事项。"
)


def _default_fake_gateway() -> FakeModelGateway:
    return FakeModelGateway(
        ResponseDraft(
            answer=_DEFAULT_OFFLINE_RESPONSE,
            next_action="ask_clarification",
            confidence=0.5,
        )
    )


def create_model_gateway(
    settings: ModelGatewaySettings | None = None,
) -> ModelGateway:
    """Create the application gateway without requiring a real provider key."""

    resolved = settings or ModelGatewaySettings.from_env()
    if resolved.api_key is None:
        return _default_fake_gateway()
    return DeepSeekGateway(resolved)


__all__ = ["create_model_gateway"]
