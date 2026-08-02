from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from backend.agent.approval_workflow import resume_refund_after_approval
from backend.agent.checkpoint import DatabaseCheckpointStore
from backend.database.base import TenantScope
from backend.domain.approval import ApprovalStatus


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
