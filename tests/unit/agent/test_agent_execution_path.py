from __future__ import annotations

from uuid import uuid4

import pytest

from backend.agent.actions import ActionDecision, ConversationActionExecutor
from backend.agent.graphs.main_graph import build_main_graph
from backend.agent.state import create_agent_state
from backend.database.base import TenantScope
from backend.domain.common import DomainError
from backend.llm.contracts import ResponseDraft
from backend.llm.fake import FakeModelGateway


class _EmptyRetriever:
    async def retrieve(self, **kwargs):
        del kwargs
        return []


class _BrokenSessionFactory:
    def __call__(self):
        raise RuntimeError("memory store unavailable")


@pytest.mark.asyncio
async def test_memory_failure_does_not_abort_and_events_use_business_thread() -> None:
    events: list[tuple[str, dict]] = []

    async def sink(event: str, data: dict) -> None:
        events.append((event, data))

    state = create_agent_state(
        scope=TenantScope(tenant_id=uuid4(), actor_id=uuid4(), actor_type="user"),
        request_id=uuid4(),
        message="客户咨询",
        thread_id="thread-business-1",
    )
    result = await build_main_graph(
        FakeModelGateway(ResponseDraft(answer="可以继续协助。", next_action="finish", confidence=0.9)),
        _BrokenSessionFactory(),
        sink,
        _EmptyRetriever(),
    ).compile().ainvoke(state)

    assert result["final_response"]
    evidence = next(data for event, data in events if event == "evidence")
    assert evidence["thread_id"] == "thread-business-1"
    assert evidence["thread_id"] != str(state.request_id)
    tokens = [data for event, data in events if event == "token"]
    assert tokens
    assert {item["thread_id"] for item in tokens} == {"thread-business-1"}


@pytest.mark.asyncio
async def test_domain_tool_domain_error_is_returned_to_the_reply() -> None:
    executor = ConversationActionExecutor(None)

    async def boom(**kwargs):
        del kwargs
        raise DomainError("workflow thread is already associated with another request")

    executor.execute = boom
    state = create_agent_state(
        scope=TenantScope(tenant_id=uuid4(), actor_id=uuid4(), actor_type="user"),
        request_id=uuid4(),
        message="我要退款",
    )

    result, clarification = await executor.run_domain_action(
        FakeModelGateway(ActionDecision(action="request_refund")),
        state,
        domain="route_billing",
        user_message="我要退款",
        thread_id="thread-1",
    )

    assert clarification is None
    assert result is not None
    assert result.action == "request_refund"
    assert "业务操作未完成" in result.summary
    assert "another request" in result.summary


@pytest.mark.asyncio
async def test_non_domain_tool_failure_still_degrades_without_raising() -> None:
    executor = ConversationActionExecutor(None)

    async def boom(**kwargs):
        del kwargs
        raise RuntimeError("database unavailable")

    executor.execute = boom
    state = create_agent_state(
        scope=TenantScope(tenant_id=uuid4()),
        request_id=uuid4(),
        message="我要退款",
    )

    result, clarification = await executor.run_domain_action(
        FakeModelGateway(ActionDecision(action="request_refund")),
        state,
        domain="route_billing",
        user_message="我要退款",
        thread_id="thread-1",
    )

    assert clarification is None
    assert result is None
