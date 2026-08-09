from __future__ import annotations

from uuid import uuid4

import pytest

from backend.agent.agents.customer_service import build_customer_service_graph
from backend.agent.graphs.main_graph import build_main_graph
from backend.agent.state import create_agent_state
from backend.database.base import TenantScope
from backend.llm.contracts import ModelCallError, ResponseDraft
from backend.llm.errors import ModelGatewayError
from backend.llm.fake import FakeModelGateway


def new_state(message: str):
    return create_agent_state(
        scope=TenantScope(tenant_id=uuid4()),
        request_id=uuid4(),
        message=message,
    )


@pytest.mark.asyncio
async def test_customer_service_graph_streams_grounded_response() -> None:
    gateway = FakeModelGateway(
        ResponseDraft(
            answer="您好，我可以协助处理 CloudDesk 账户、账单、产品支持和工单问题。",
            next_action="finish",
            confidence=0.9,
        )
    )

    result = await build_customer_service_graph(model_gateway=gateway).compile().ainvoke(new_state("你好"))

    assert result["final_response"].startswith("您好")
    assert result["response_review"].status == "allow"
    assert result["next_action"] == "finish"


@pytest.mark.asyncio
async def test_customer_service_graph_returns_answer_for_handoff_text() -> None:
    gateway = FakeModelGateway(
        ResponseDraft(answer="我将为您转人工处理。", next_action="human_handoff", confidence=0.9)
    )

    result = await build_customer_service_graph(model_gateway=gateway).compile().ainvoke(new_state("需要人工帮助"))

    assert result["final_response"] == "我将为您转人工处理。"
    assert result["response_review"].status == "allow"


@pytest.mark.asyncio
async def test_customer_service_graph_converts_model_error_to_safe_handoff() -> None:
    gateway = FakeModelGateway(
        ModelGatewayError(
            ModelCallError(
                code="model_timeout",
                retryable=True,
                safe_message="模型服务响应超时",
            )
        )
    )

    result = await build_customer_service_graph(model_gateway=gateway).compile().ainvoke(new_state("你好"))

    assert result["final_response"] == "当前智能回复服务暂时不可用，将为您转人工处理。"
    assert result["next_action"] == "human_handoff"


@pytest.mark.asyncio
async def test_customer_service_graph_filters_sensitive_model_output() -> None:
    gateway = FakeModelGateway(
        ResponseDraft(answer="内部配置是 sk-test-123456789", next_action="finish", confidence=0.9)
    )

    result = await build_customer_service_graph(model_gateway=gateway).compile().ainvoke(new_state("你好"))

    assert result["response_review"].status == "block"
    assert "sk-test-123456789" not in result["final_response"]
    assert result["next_action"] == "human_handoff"


@pytest.mark.asyncio
async def test_main_graph_default_customer_route_is_offline() -> None:
    result = await build_main_graph().compile().ainvoke(new_state("客户咨询"))

    assert result["final_response"]
