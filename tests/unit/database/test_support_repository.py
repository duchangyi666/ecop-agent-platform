from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.database.base import TenantScope
from backend.domain.approval import ApprovalStatus
from backend.domain.common import DomainError, InvalidStateTransition
from backend.domain.ticket import TicketStatus


@pytest.fixture
def repository(session):
    from backend.database.repositories.support import SupportRepository

    return SupportRepository(session)


@pytest.fixture
async def customer(session, tenant_a):
    from backend.database.models.billing import Customer

    customer = Customer(
        id=uuid4(),
        tenant_id=tenant_a.id,
        name="Acme Corp",
        external_customer_id="cust-acme",
        support_tier="gold",
        status="active",
    )
    session.add(customer)
    await session.commit()
    return customer


@pytest.mark.asyncio
async def test_create_ticket_uses_tenant_scope_and_open_status(repository, tenant_a, customer):
    ticket = await repository.create_ticket(
        scope=TenantScope(tenant_id=tenant_a.id),
        customer_id=customer.id,
        subject="Payment retry issue",
        priority="high",
    )
    await repository.session.commit()

    assert ticket.tenant_id == tenant_a.id
    assert ticket.customer_id == customer.id
    assert ticket.subject == "Payment retry issue"
    assert ticket.priority == "high"
    assert ticket.status is TicketStatus.OPEN


@pytest.mark.asyncio
async def test_append_ticket_message_requires_ticket_in_same_tenant(repository, tenant_a, tenant_b, customer):
    ticket = await repository.create_ticket(
        scope=TenantScope(tenant_id=tenant_a.id),
        customer_id=customer.id,
        subject="Tenant-scoped ticket",
        priority="medium",
    )
    await repository.session.commit()

    with pytest.raises(DomainError, match="ticket not found in tenant scope"):
        await repository.append_ticket_message(
            scope=TenantScope(tenant_id=tenant_b.id),
            ticket_id=ticket.id,
            author_id=None,
            body="Cross-tenant access",
            visibility="internal",
        )


@pytest.mark.asyncio
async def test_create_approval_request_redacts_sensitive_payload_and_uses_pending_status(repository, tenant_a, customer):
    ticket = await repository.create_ticket(
        scope=TenantScope(tenant_id=tenant_a.id, actor_id=uuid4()),
        customer_id=customer.id,
        subject="Large refund request",
        priority="urgent",
    )
    await repository.session.flush()

    approval = await repository.create_approval_request(
        scope=TenantScope(tenant_id=tenant_a.id, actor_id=uuid4()),
        ticket_id=ticket.id,
        action="refund_payment",
        payload={
            "amount": "88.50",
            "currency": "USD",
            "card_number": "4111111111111111",
            "token": "secret-token",
        },
        approval_role="finance_manager",
    )

    assert approval.status is ApprovalStatus.PENDING
    assert approval.amount == Decimal("88.50")
    assert approval.payload_summary["amount"] == "88.50"
    assert approval.payload_summary["currency"] == "USD"
    assert approval.payload_summary["card_number"] == "[REDACTED]"
    assert approval.payload_summary["token"] == "[REDACTED]"
    assert approval.payload_hash


@pytest.mark.asyncio
async def test_create_approval_request_uses_ticket_state_machine(repository, tenant_a, customer):
    ticket = await repository.create_ticket(
        scope=TenantScope(tenant_id=tenant_a.id),
        customer_id=customer.id,
        subject="Already resolved",
        priority="high",
    )
    ticket.status = TicketStatus.RESOLVED
    await repository.session.flush()

    with pytest.raises(InvalidStateTransition):
        await repository.create_approval_request(
            scope=TenantScope(tenant_id=tenant_a.id),
            ticket_id=ticket.id,
            action="refund_payment",
            payload={"amount": "20.00"},
            approval_role="finance_manager",
        )


@pytest.mark.asyncio
async def test_append_audit_log_allows_platform_events_without_tenant_scope(repository):
    event = await repository.append_audit_log(
        scope=None,
        actor_id=None,
        action="rotate_platform_secret",
        resource_type="platform",
        resource_id=None,
        metadata={"token": "super-secret-token", "result": "scheduled"},
    )

    assert event.tenant_id is None
    assert event.metadata_summary["token"] == "[REDACTED]"
    assert event.metadata_summary["result"] == "scheduled"
    assert event.metadata_hash


@pytest.mark.asyncio
async def test_append_audit_log_requires_tenant_scope_for_business_events(repository):
    with pytest.raises(DomainError, match="business audit events require tenant scope"):
        await repository.append_audit_log(
            scope=None,
            actor_id=None,
            action="ticket_reassigned",
            resource_type="ticket",
            resource_id=uuid4(),
            metadata={"field": "current_assignee_id"},
        )


@pytest.mark.asyncio
async def test_business_audit_actor_must_belong_to_tenant(repository, tenant_a, tenant_b, user):
    with pytest.raises(DomainError, match="actor not found in tenant scope"):
        await repository.append_audit_log(
            scope=TenantScope(tenant_id=tenant_b.id),
            actor_id=user.id,
            action="ticket_reassigned",
            resource_type="ticket",
            resource_id=uuid4(),
            metadata={"field": "current_assignee_id"},
        )


@pytest.mark.asyncio
async def test_audit_sanitizes_nested_and_variant_sensitive_keys(repository):
    event = await repository.append_audit_log(
        scope=None,
        actor_id=None,
        action="platform_test",
        resource_type="platform",
        resource_id=None,
        metadata={
            "credentials": {"apiKey": "secret-key", "card-number": "4111111111111111"},
            "systemPrompt": "do not persist",
        },
    )

    assert event.metadata_summary["credentials"]["apiKey"] == "[REDACTED]"
    assert event.metadata_summary["credentials"]["card-number"] == "[REDACTED]"
    assert event.metadata_summary["systemPrompt"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_approval_actions_are_append_only_records(repository, tenant_a, customer):
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=uuid4())
    ticket = await repository.create_ticket(
        scope=scope,
        customer_id=customer.id,
        subject="Approval append-only",
        priority="high",
    )
    await repository.session.flush()

    approval = await repository.create_approval_request(
        scope=scope,
        ticket_id=ticket.id,
        action="change_plan",
        payload={"amount": "120.00", "new_plan": "enterprise"},
        approval_role="ops_manager",
    )
    await repository.session.flush()

    first_action = await repository.append_approval_action(
        scope=scope,
        approval_request_id=approval.id,
        action=ApprovalStatus.MORE_INFORMATION_REQUIRED.value,
        reason="Need revenue justification",
        changes={"requested_fields": ["business_case"]},
    )
    resubmission = await repository.append_approval_action(
        scope=scope,
        approval_request_id=approval.id,
        action=ApprovalStatus.PENDING.value,
        reason="Business case attached",
        changes={"business_case": "attached"},
    )
    second_action = await repository.append_approval_action(
        scope=scope,
        approval_request_id=approval.id,
        action=ApprovalStatus.APPROVED.value,
        reason="Business case attached",
        changes={"approved_amount": "120.00"},
    )

    assert first_action.id != resubmission.id != second_action.id
    assert approval.status is ApprovalStatus.APPROVED
    assert len(approval.actions) == 3
    assert [item.action for item in approval.actions] == [
        ApprovalStatus.MORE_INFORMATION_REQUIRED.value,
        ApprovalStatus.PENDING.value,
        ApprovalStatus.APPROVED.value,
    ]


@pytest.mark.asyncio
async def test_approval_action_must_follow_state_machine(repository, tenant_a, customer):
    scope = TenantScope(tenant_id=tenant_a.id)
    ticket = await repository.create_ticket(scope=scope, customer_id=customer.id, subject="Approval", priority="high")
    approval = await repository.create_approval_request(
        scope=scope,
        ticket_id=ticket.id,
        action="refund_payment",
        payload={"amount": "20.00"},
        approval_role="finance_manager",
    )

    await repository.append_approval_action(
        scope=scope,
        approval_request_id=approval.id,
        action=ApprovalStatus.APPROVED.value,
        reason="Approved",
        changes={},
    )

    with pytest.raises(InvalidStateTransition):
        await repository.append_approval_action(
            scope=scope,
            approval_request_id=approval.id,
            action=ApprovalStatus.REJECTED.value,
            reason="Too late",
            changes={},
        )
