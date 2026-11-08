from __future__ import annotations

from uuid import uuid4

import pytest

from backend.agent.actions import (
    CUSTOMER_TOOL_FAILURE_SUMMARY,
    ActionDecision,
    ActionResult,
    ConversationActionExecutor,
)
from backend.agent.graphs.main_graph import build_main_graph
from backend.agent.state import create_agent_state
from backend.database.base import TenantScope
from backend.domain.common import DomainError
from backend.llm.contracts import ModelUsage, ResponseDraft
from backend.llm.fake import FakeModelGateway


class _BillingRouteGateway(FakeModelGateway):
    def __init__(self, answer: str) -> None:
        super().__init__(ResponseDraft(answer=answer, next_action="finish", confidence=0.9))

    async def generate_structured(self, *, system_prompt, user_prompt, response_model):
        del system_prompt, user_prompt
        self.call_count += 1
        usage = ModelUsage(provider="fake", model="fake", latency_ms=0)
        if response_model.__name__ == "RouteDecision":
            return response_model(route="route_billing"), usage
        if response_model.__name__ == "ActionDecision":
            return response_model(action="answer"), usage
        return response_model.model_validate(self.response.model_dump()), usage


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
    assert result.summary == CUSTOMER_TOOL_FAILURE_SUMMARY
    assert "another request" not in result.summary
    assert "workflow" not in result.summary


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


class _SessionFactory:
    def __call__(self):
        raise AssertionError("domain tool should be stubbed")


@pytest.mark.asyncio
async def test_recorded_refund_approval_ends_as_human_handoff(monkeypatch) -> None:
    approval_id = uuid4()

    async def approved(self, gateway, state, *, domain, user_message, thread_id):
        del self, gateway, state, domain, user_message, thread_id
        return ActionResult(
            action="request_refund",
            summary="退款申请已登记，已提交财务经理审批。",
            approval_request_id=approval_id,
            refund_id=uuid4(),
        ), None

    monkeypatch.setattr(ConversationActionExecutor, "run_domain_action", approved)
    state = create_agent_state(
        scope=TenantScope(tenant_id=uuid4()),
        request_id=uuid4(),
        message="我要申请退款",
        thread_id="thread-approval-1",
    )
    result = await build_main_graph(
        _BillingRouteGateway("不应覆盖审批说明。"),
        _SessionFactory(),
        None,
        _EmptyRetriever(),
    ).compile().ainvoke(state)

    assert result["status"] == "human_handoff"
    assert result["next_action"] == "human_handoff"
    assert result["final_response"] == "退款申请已登记，已提交财务经理审批。"
    assert "不应覆盖审批说明" not in result["final_response"]


@pytest.mark.asyncio
async def test_refund_without_approval_is_not_forced_to_handoff(monkeypatch) -> None:
    async def preview_only(self, gateway, state, *, domain, user_message, thread_id):
        del self, gateway, state, domain, user_message, thread_id
        return ActionResult(action="request_refund", summary="未发现重复扣费，暂不发起退款。"), None

    monkeypatch.setattr(ConversationActionExecutor, "run_domain_action", preview_only)
    state = create_agent_state(
        scope=TenantScope(tenant_id=uuid4()),
        request_id=uuid4(),
        message="我要申请退款",
    )
    result = await build_main_graph(
        _BillingRouteGateway("已核对账单。"),
        _SessionFactory(),
        None,
        _EmptyRetriever(),
    ).compile().ainvoke(state)

    assert result["status"] == "completed"
    assert result["next_action"] == "finish"
    assert result["final_response"] == "已核对账单。"
