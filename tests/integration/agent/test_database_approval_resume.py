from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.agent.approval_workflow import resume_refund_after_approval
from backend.agent.checkpoint import DatabaseCheckpointStore
from backend.database.base import TenantScope
from backend.database.models.governance import WorkflowCheckpoint
from backend.database.models.support import ApprovalAction, ApprovalRequest
from backend.database.repositories.governance import GovernanceRepository
from backend.domain.approval import ApprovalStatus
from backend.domain.common import DomainError


@pytest.mark.asyncio
async def test_database_checkpoint_survives_store_recreation(session_factory, tenant_a, tenant_a_user):
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    payload = {
        "state": {"next_action": "human_handoff", "refund_id": str(uuid4())},
        "refund_idempotency_key": f"checkpoint-{uuid4().hex}",
        "status": "awaiting_approval",
    }

    first_store = DatabaseCheckpointStore(session_factory, scope)
    await first_store.save("thread-db-checkpoint-1", payload)
    second_store = DatabaseCheckpointStore(session_factory, scope)
    restored = await second_store.load("thread-db-checkpoint-1")

    assert restored is not None
    assert restored["refund_idempotency_key"] == payload["refund_idempotency_key"]
    assert restored["state"]["next_action"] == "human_handoff"


@pytest.mark.asyncio
async def test_approved_refund_resume_keeps_original_idempotency_key(
    database_url,
    uow,
    payment,
    tenant_a,
    tenant_a_user,
):
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    idempotency_key = f"resume-{uuid4().hex}"
    refund = await uow.billing.create_refund_request(
        scope=scope,
        payment_id=payment.id,
        idempotency_key=idempotency_key,
        amount=Decimal("20.00"),
    )
    approval = await uow.support.create_refund_approval_request(
        scope=scope,
        refund_id=refund.id,
        action="approve_refund",
        payload={"amount": "20.00", "refund_id": str(refund.id)},
        approval_role="finance_manager",
        checkpoint_reference="thread-resume-1",
    )
    await uow.governance.save_workflow_checkpoint(
        scope=scope,
        thread_id="thread-resume-1",
        state_summary={"refund_id": str(refund.id), "approval_request_id": str(approval.id)},
        refund_idempotency_key=idempotency_key,
        status="awaiting_approval",
        trace_id=None,
    )
    await uow.commit()

    result = await resume_refund_after_approval(
        database_url=database_url,
        scope=scope,
        thread_id="thread-resume-1",
        approval_request_id=approval.id,
        approved=True,
        actor_id=tenant_a_user.id,
    )

    assert result.status == "approved_for_execution"
    assert result.refund_idempotency_key == idempotency_key
    assert result.refund_id == refund.id


@pytest.mark.asyncio
async def test_rejected_refund_resume_does_not_mark_approval_approved(
    database_url,
    uow,
    payment,
    tenant_a,
    tenant_a_user,
):
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    refund = await uow.billing.create_refund_request(
        scope=scope,
        payment_id=payment.id,
        idempotency_key=f"reject-{uuid4().hex}",
        amount=Decimal("20.00"),
    )
    approval = await uow.support.create_refund_approval_request(
        scope=scope,
        refund_id=refund.id,
        action="approve_refund",
        payload={"amount": "20.00"},
        approval_role="finance_manager",
        checkpoint_reference="thread-reject-1",
    )
    await uow.governance.save_workflow_checkpoint(
        scope=scope,
        thread_id="thread-reject-1",
        state_summary={"refund_id": str(refund.id), "approval_request_id": str(approval.id)},
        refund_idempotency_key=refund.idempotency_key,
        status="awaiting_approval",
        trace_id=None,
    )
    await uow.commit()

    result = await resume_refund_after_approval(
        database_url=database_url,
        scope=scope,
        thread_id="thread-reject-1",
        approval_request_id=approval.id,
        approved=False,
        actor_id=tenant_a_user.id,
    )

    assert result.status == "rejected"
    assert result.refund_id == refund.id
    assert result.approval_request_id == approval.id


@pytest.mark.asyncio
async def test_concurrent_decisions_record_only_one_action(
    database_url, uow, payment, tenant_a, tenant_a_user, session_factory, monkeypatch,
):
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    refund = await uow.billing.create_refund_request(
        scope=scope, payment_id=payment.id, idempotency_key=f"race-{uuid4().hex}",
        amount=Decimal("20.00"),
    )
    thread_id = f"race-{uuid4().hex}"
    approval = await uow.support.create_refund_approval_request(
        scope=scope, refund_id=refund.id, action="approve_refund",
        payload={"amount": "20.00"}, approval_role="finance_manager",
        checkpoint_reference=thread_id,
    )
    await uow.governance.save_workflow_checkpoint(
        scope=scope, thread_id=thread_id,
        state_summary={"refund_id": str(refund.id), "approval_request_id": str(approval.id)},
        refund_idempotency_key=refund.idempotency_key, status="awaiting_approval", trace_id=None,
    )
    await uow.commit()

    first_read = asyncio.Event()
    release_first = asyncio.Event()
    original = GovernanceRepository.get_workflow_checkpoint

    async def hold_first_read(self, **kwargs):
        result = await original(self, **kwargs)
        if not first_read.is_set():
            first_read.set()
            await release_first.wait()
        return result

    monkeypatch.setattr(GovernanceRepository, "get_workflow_checkpoint", hold_first_read)

    def decide(approved):
        return resume_refund_after_approval(
            database_url=database_url, scope=scope, thread_id=thread_id,
            approval_request_id=approval.id, approved=approved, actor_id=tenant_a_user.id,
        )

    first = asyncio.create_task(decide(True))
    second = None
    try:
        await asyncio.wait_for(first_read.wait(), timeout=10)
        second = asyncio.create_task(decide(False))
        try:
            await asyncio.wait_for(asyncio.shield(second), timeout=1)
        except (TimeoutError, DomainError):
            pass
    finally:
        release_first.set()
    outcomes = await asyncio.gather(first, second, return_exceptions=True)
    assert sum(isinstance(outcome, DomainError) for outcome in outcomes) == 1
    assert sum(not isinstance(outcome, BaseException) for outcome in outcomes) == 1
    async with session_factory() as session:
        stored = await session.get(ApprovalRequest, approval.id)
        actions = list(await session.scalars(
            select(ApprovalAction).where(ApprovalAction.approval_request_id == approval.id)
        ))
        assert len(actions) == 1
        assert stored.status.value == actions[0].action
        checkpoint = await session.scalar(
            select(WorkflowCheckpoint).where(WorkflowCheckpoint.thread_id == thread_id)
        )
        expected_status = "approved_for_execution" if actions[0].action == "approved" else "rejected"
        assert checkpoint.status == expected_status
