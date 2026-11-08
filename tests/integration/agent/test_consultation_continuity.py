from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from backend.agent.actions import (
    CUSTOMER_TOOL_FAILURE_SUMMARY,
    ActionDecision,
    ConversationActionExecutor,
)
from backend.agent.consultation_workflow import (
    CustomerConsultationService,
    CustomerConsultationWorkflowRequest,
    load_consultation_history,
)
from backend.agent.state import create_agent_state
from backend.database.base import TenantScope
from backend.database.models.billing import CustomerContact, Payment
from backend.database.models.governance import ToolExecution, WorkflowCheckpoint
from backend.database.models.identity import Permission, Role, UserRole
from backend.database.models.support import ApprovalRequest, Conversation, ConversationMessage
from backend.database.unit_of_work import UnitOfWork
from backend.domain.common import DomainError
from backend.llm.contracts import ModelUsage, ResponseDraft
from backend.llm.fake import FakeModelGateway


class _EmptyRetriever:
    async def retrieve(self, **kwargs):
        del kwargs
        return []


class _BlockingGateway(FakeModelGateway):
    def __init__(self) -> None:
        super().__init__(ResponseDraft(answer="不会返回", next_action="finish", confidence=0.9))
        self.started = asyncio.Event()

    async def generate_structured(self, **kwargs):
        self.started.set()
        await asyncio.Event().wait()
        return await super().generate_structured(**kwargs)


class _RefundGateway(FakeModelGateway):
    def __init__(self) -> None:
        super().__init__(ResponseDraft(answer="已提交退款申请。", next_action="finish", confidence=0.9))

    async def generate_structured(self, *, system_prompt, user_prompt, response_model):
        del system_prompt, user_prompt
        self.call_count += 1
        usage = ModelUsage(provider="fake", model="fake", latency_ms=0)
        if response_model.__name__ == "RouteDecision":
            return response_model(route="route_billing"), usage
        if response_model.__name__ == "ActionDecision":
            return response_model(action="request_refund", ready=True), usage
        return response_model.model_validate(self.response.model_dump()), usage


async def _grant(session_factory, tenant_id, user_id, code: str) -> None:
    async with session_factory() as session:
        role_id = uuid4()
        session.add(Role(
            id=role_id, tenant_id=tenant_id, code=f"role-{uuid4().hex[:8]}",
            name=code, status="active", is_platform_role=False,
        ))
        session.add(Permission(
            id=uuid4(), tenant_id=tenant_id, role_id=role_id, code=code, name=code, status="active",
        ))
        session.add(UserRole(id=uuid4(), tenant_id=tenant_id, user_id=user_id, role_id=role_id))
        await session.commit()


@pytest.mark.asyncio
async def test_history_restores_turns_when_timestamps_and_ids_disagree(
    session_factory, tenant_a, tenant_a_user,
) -> None:
    later = datetime.now(timezone.utc)
    earlier = later - timedelta(minutes=5)
    conversation_id = uuid4()
    async with session_factory() as session:
        session.add(Conversation(
            id=conversation_id, tenant_id=tenant_a.id, user_id=tenant_a_user.id,
            thread_id=f"order-{uuid4().hex}", channel="ai_chat", subject="顺序", status="open",
        ))
        session.add(ConversationMessage(
            id=UUID("ffffffff-ffff-4fff-bfff-ffffffffffff"),
            tenant_id=tenant_a.id, conversation_id=conversation_id, author_id=tenant_a_user.id,
            author_type="user", role="user", body="甲", visibility="public",
            turn_sequence=1, created_at=later,
        ))
        session.add(ConversationMessage(
            id=UUID("00000000-0000-4000-8000-000000000001"),
            tenant_id=tenant_a.id, conversation_id=conversation_id, author_id=None,
            author_type="agent", role="assistant", body="甲回复", visibility="public",
            turn_sequence=1, created_at=later,
        ))
        session.add(ConversationMessage(
            id=UUID("00000000-0000-4000-8000-000000000002"),
            tenant_id=tenant_a.id, conversation_id=conversation_id, author_id=tenant_a_user.id,
            author_type="user", role="user", body="乙", visibility="public",
            turn_sequence=2, created_at=earlier,
        ))
        await session.commit()
        restored = await load_consultation_history(
            session, tenant_id=tenant_a.id, conversation_id=conversation_id,
            actor_id=tenant_a_user.id, limit=20,
        )

    assert [item.content for item in restored] == ["甲", "甲回复", "乙"]


@pytest.mark.asyncio
async def test_history_limit_counts_messages_not_turns(
    session_factory, tenant_a, tenant_a_user,
) -> None:
    conversation_id = uuid4()
    base = datetime.now(timezone.utc)
    async with session_factory() as session:
        session.add(Conversation(
            id=conversation_id, tenant_id=tenant_a.id, user_id=tenant_a_user.id,
            thread_id=f"limit-{uuid4().hex}", channel="ai_chat", subject="上限", status="open",
        ))
        for turn in range(1, 13):
            created = base + timedelta(seconds=turn)
            session.add(ConversationMessage(
                tenant_id=tenant_a.id, conversation_id=conversation_id, author_id=tenant_a_user.id,
                author_type="user", role="user", body=f"u{turn}", visibility="public",
                turn_sequence=turn, created_at=created,
            ))
            session.add(ConversationMessage(
                tenant_id=tenant_a.id, conversation_id=conversation_id, author_id=None,
                author_type="agent", role="assistant", body=f"a{turn}", visibility="public",
                turn_sequence=turn, created_at=created + timedelta(microseconds=1),
            ))
        await session.commit()
        capped = await load_consultation_history(
            session, tenant_id=tenant_a.id, conversation_id=conversation_id,
            actor_id=tenant_a_user.id, limit=20,
        )
        odd_window = await load_consultation_history(
            session, tenant_id=tenant_a.id, conversation_id=conversation_id,
            actor_id=tenant_a_user.id, limit=5,
        )

    assert [item.content for item in capped] == [f"{role}{turn}" for turn in range(3, 13) for role in ("u", "a")]
    assert len(capped) == 20
    assert [item.content for item in odd_window] == ["u11", "a11", "u12", "a12"]


@pytest.mark.asyncio
async def test_append_same_turn_and_role_keeps_the_first_reply(
    session_factory, tenant_a, tenant_a_user,
) -> None:
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    async with UnitOfWork(session_factory, scope=scope) as uow:
        conversation = await uow.support.create_conversation(
            scope=scope, customer_id=None, user_id=tenant_a_user.id, channel="ai_chat", subject="幂等",
        )
        user = await uow.support.append_conversation_message(
            scope=scope, conversation_id=conversation.id, author_id=tenant_a_user.id,
            author_type="user", role="user", body="问", visibility="public",
        )
        first = await uow.support.append_conversation_message(
            scope=scope, conversation_id=conversation.id, author_id=None,
            author_type="agent", role="assistant", body="第一次", visibility="public",
            turn_sequence=user.turn_sequence,
        )
        second = await uow.support.append_conversation_message(
            scope=scope, conversation_id=conversation.id, author_id=None,
            author_type="agent", role="assistant", body="第二次", visibility="public",
            turn_sequence=user.turn_sequence,
        )
        stored = list(await uow.session.scalars(
            select(ConversationMessage).where(ConversationMessage.conversation_id == conversation.id)
        ))
    assert first.id == second.id
    assert second.body == "第一次"
    assert len(stored) == 2


@pytest.mark.asyncio
async def test_cancelled_consultation_keeps_the_user_turn(
    session_factory, tenant_a, tenant_a_user,
) -> None:
    gateway = _BlockingGateway()
    service = CustomerConsultationService(
        session_factory, model_gateway=gateway, knowledge_retriever=_EmptyRetriever(),
    )
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    thread_id = f"cancel-{uuid4().hex}"
    request = CustomerConsultationWorkflowRequest(
        thread_id=thread_id,
        state=create_agent_state(scope=scope, request_id=uuid4(), message="客户咨询"),
    )
    task = asyncio.create_task(service.run(request))
    await asyncio.wait_for(gateway.started.wait(), timeout=10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert service.turn_cleanup is not None
    await service.turn_cleanup

    async with session_factory() as session:
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == thread_id))
        restored = await load_consultation_history(
            session, tenant_id=tenant_a.id, conversation_id=conversation.id,
            actor_id=tenant_a_user.id, limit=20,
        )
    assert [item.role for item in restored] == ["user", "assistant"]
    assert restored[0].content == "客户咨询"
    assert "中断" in restored[1].content


@pytest.mark.asyncio
async def test_failed_consultation_closes_the_user_turn(
    session_factory, tenant_a, tenant_a_user,
) -> None:
    async def sink(event: str, data: dict) -> None:
        del data
        if event == "evidence":
            raise RuntimeError("stream broke")

    service = CustomerConsultationService(
        session_factory,
        model_gateway=FakeModelGateway(ResponseDraft(answer="不会用到", next_action="finish", confidence=0.9)),
        knowledge_retriever=_EmptyRetriever(),
        event_sink=sink,
    )
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    thread_id = f"fail-{uuid4().hex}"
    with pytest.raises(RuntimeError, match="stream broke"):
        await service.run(CustomerConsultationWorkflowRequest(
            thread_id=thread_id,
            state=create_agent_state(scope=scope, request_id=uuid4(), message="客户咨询"),
        ))
    async with session_factory() as session:
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == thread_id))
        restored = await load_consultation_history(
            session, tenant_id=tenant_a.id, conversation_id=conversation.id,
            actor_id=tenant_a_user.id, limit=20,
        )
    assert [item.content for item in restored] == ["客户咨询", "处理没有完成，请稍后重试。"]


@pytest.mark.asyncio
async def test_chat_refund_checkpoint_uses_conversation_thread_and_audits_the_tool(
    session_factory, tenant_a, tenant_a_user, payment,
) -> None:
    await _grant(session_factory, tenant_a.id, tenant_a_user.id, "refund.request")
    async with session_factory() as session:
        stored = await session.get(Payment, payment.id)
        stored.amount = Decimal("1500.00")
        session.add(CustomerContact(
            tenant_id=tenant_a.id, customer_id=payment.customer_id, user_id=tenant_a_user.id,
            channel="email", masked_value="test@example.invalid", contact_hash=uuid4().hex,
            preferred_language="zh-CN",
        ))
        session.add(Payment(
            tenant_id=tenant_a.id, customer_id=payment.customer_id, invoice_id=payment.invoice_id,
            external_payment_id=f"dup-{uuid4().hex}", amount=Decimal("1500.00"),
            currency=payment.currency, status=payment.status, paid_at=payment.paid_at + timedelta(minutes=1),
        ))
        await session.commit()

    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    request_id = uuid4()
    thread_id = f"refund-thread-{uuid4().hex[:8]}"
    service = CustomerConsultationService(
        session_factory,
        model_gateway=_RefundGateway(),
        knowledge_retriever=_EmptyRetriever(),
    )
    result = await service.run(CustomerConsultationWorkflowRequest(
        thread_id=thread_id,
        state=create_agent_state(
            scope=scope, request_id=request_id, message="我被重复扣费了要退款",
        ),
    ))
    assert result.status == "human_handoff"
    assert result.next_action == "human_handoff"
    assert result.final_response
    assert "审批" in result.final_response
    assert "已提交退款申请" not in (result.final_response or "")

    async with session_factory() as session:
        checkpoint = await session.scalar(
            select(WorkflowCheckpoint).where(
                WorkflowCheckpoint.tenant_id == tenant_a.id,
                WorkflowCheckpoint.thread_id == thread_id,
            )
        )
        approval = await session.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.tenant_id == tenant_a.id,
                ApprovalRequest.checkpoint_reference == thread_id,
            )
        )
        execution = await session.scalar(
            select(ToolExecution).where(
                ToolExecution.tenant_id == tenant_a.id,
                ToolExecution.tool_name == "billing.request",
            )
        )
    assert checkpoint is not None
    assert checkpoint.thread_id != str(request_id)
    assert checkpoint.status == "awaiting_approval"
    assert approval is not None and approval.checkpoint_reference == thread_id
    assert execution is not None and execution.status == "succeeded"
    assert execution.trace_id is not None


@pytest.mark.asyncio
async def test_failed_domain_tool_is_audited(
    session_factory, tenant_a, tenant_a_user,
) -> None:
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    async with UnitOfWork(session_factory, scope=scope) as uow:
        trace = await uow.governance.create_runtime_trace(
            scope=scope, trace_key=f"tool-fail-{uuid4().hex}", entrypoint="agent.test",
            input_summary="tool failure", input_hash=uuid4().hex,
        )
        trace_id = trace.id
    executor = ConversationActionExecutor(session_factory)

    async def boom(**kwargs):
        del kwargs
        raise DomainError("payment not found in customer scope")

    executor.execute = boom
    state = create_agent_state(scope=scope, request_id=uuid4(), message="我要退款").model_copy(
        update={"trace_id": trace_id}
    )
    result, clarification = await executor.run_domain_action(
        FakeModelGateway(ActionDecision(action="request_refund")),
        state,
        domain="route_billing",
        user_message="我要退款",
        thread_id="thread-tool-fail",
    )
    assert clarification is None
    assert result is not None
    assert result.summary == CUSTOMER_TOOL_FAILURE_SUMMARY
    assert "payment not found" not in result.summary
    async with session_factory() as session:
        execution = await session.scalar(select(ToolExecution).where(ToolExecution.trace_id == trace_id))
    assert execution is not None
    assert execution.status == "failed"
    assert execution.tool_name == "billing.request"
    assert "payment not found" in (execution.error_summary or "")
    assert "payment not found" not in str(execution.result_summary)
