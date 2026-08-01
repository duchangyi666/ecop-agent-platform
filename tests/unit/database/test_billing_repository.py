from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from backend.database.base import TenantScope
from backend.domain.common import DomainError
from backend.domain.billing import PaymentStatus, RefundStatus
from backend.database.models.billing import Customer, Invoice, Payment, Refund
from backend.database.repositories.billing import BillingRepository


@pytest.fixture
def repository(session):
    return BillingRepository(session)


async def _create_customer(session, *, tenant_id):
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant_id,
        name="Acme Corp",
        external_customer_id=f"ext-{uuid4()}",
        support_tier="standard",
        status="active",
    )
    session.add(customer)
    await session.flush()
    return customer


async def _create_invoice(session, *, tenant_id, customer_id, amount: Decimal):
    invoice = Invoice(
        id=uuid4(),
        tenant_id=tenant_id,
        customer_id=customer_id,
        subscription_id=None,
        amount=amount,
        currency="CNY",
        status="issued",
        issued_at=datetime.now(timezone.utc),
    )
    session.add(invoice)
    await session.flush()
    return invoice


async def _create_payment(
    session,
    *,
    tenant_id,
    customer_id,
    invoice_id,
    amount: Decimal,
    status: PaymentStatus = PaymentStatus.SUCCEEDED,
    paid_at: datetime | None = None,
    deleted_at: datetime | None = None,
):
    payment = Payment(
        id=uuid4(),
        tenant_id=tenant_id,
        customer_id=customer_id,
        invoice_id=invoice_id,
        external_payment_id=f"pay-{uuid4()}",
        amount=amount,
        currency="CNY",
        status=status,
        paid_at=paid_at or datetime.now(timezone.utc),
        deleted_at=deleted_at,
    )
    session.add(payment)
    await session.flush()
    return payment


@pytest.mark.asyncio
async def test_get_payment_for_tenant_requires_same_tenant(repository, session, tenant_a, tenant_b):
    customer = await _create_customer(session, tenant_id=tenant_a.id)
    invoice = await _create_invoice(session, tenant_id=tenant_a.id, customer_id=customer.id, amount=Decimal("88.00"))
    payment = await _create_payment(
        session,
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        invoice_id=invoice.id,
        amount=Decimal("88.00"),
    )
    await session.commit()

    result = await repository.get_payment_for_tenant(
        scope=TenantScope(tenant_id=tenant_b.id),
        payment_id=payment.id,
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_payment_for_tenant_ignores_soft_deleted_rows(repository, session, tenant_a):
    customer = await _create_customer(session, tenant_id=tenant_a.id)
    invoice = await _create_invoice(session, tenant_id=tenant_a.id, customer_id=customer.id, amount=Decimal("88.00"))
    payment = await _create_payment(
        session,
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        invoice_id=invoice.id,
        amount=Decimal("88.00"),
        deleted_at=datetime.now(timezone.utc),
    )
    await session.commit()

    result = await repository.get_payment_for_tenant(
        scope=TenantScope(tenant_id=tenant_a.id),
        payment_id=payment.id,
    )

    assert result is None


@pytest.mark.asyncio
async def test_find_duplicate_charge_returns_same_tenant_same_customer_same_amount_inside_window(
    repository, session, tenant_a, tenant_b
):
    customer = await _create_customer(session, tenant_id=tenant_a.id)
    invoice = await _create_invoice(session, tenant_id=tenant_a.id, customer_id=customer.id, amount=Decimal("88.00"))
    occurred_at = datetime.now(timezone.utc)

    expected = await _create_payment(
        session,
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        invoice_id=invoice.id,
        amount=Decimal("88.00"),
        status=PaymentStatus.REQUIRES_ACTION,
        paid_at=occurred_at - timedelta(minutes=3),
    )
    await _create_payment(
        session,
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        invoice_id=invoice.id,
        amount=Decimal("88.00"),
        paid_at=occurred_at - timedelta(minutes=6),
    )
    await _create_payment(
        session,
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        invoice_id=invoice.id,
        amount=Decimal("18.00"),
        paid_at=occurred_at - timedelta(minutes=2),
    )
    other_customer = await _create_customer(session, tenant_id=tenant_a.id)
    other_invoice = await _create_invoice(session, tenant_id=tenant_a.id, customer_id=other_customer.id, amount=Decimal("88.00"))
    await _create_payment(
        session,
        tenant_id=tenant_a.id,
        customer_id=other_customer.id,
        invoice_id=other_invoice.id,
        amount=Decimal("88.00"),
        paid_at=occurred_at - timedelta(minutes=2),
    )
    tenant_b_customer = await _create_customer(session, tenant_id=tenant_b.id)
    tenant_b_invoice = await _create_invoice(session, tenant_id=tenant_b.id, customer_id=tenant_b_customer.id, amount=Decimal("88.00"))
    await _create_payment(
        session,
        tenant_id=tenant_b.id,
        customer_id=tenant_b_customer.id,
        invoice_id=tenant_b_invoice.id,
        amount=Decimal("88.00"),
        paid_at=occurred_at - timedelta(minutes=2),
    )
    await _create_payment(
        session,
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        invoice_id=invoice.id,
        amount=Decimal("88.00"),
        paid_at=occurred_at - timedelta(minutes=2),
        deleted_at=datetime.now(timezone.utc),
    )
    await session.commit()

    duplicates = await repository.find_duplicate_charge(
        scope=TenantScope(tenant_id=tenant_a.id),
        customer_id=customer.id,
        amount=Decimal("88.00"),
        occurred_at=occurred_at,
    )

    assert [item.id for item in duplicates] == [expected.id]


@pytest.mark.asyncio
async def test_get_refund_by_idempotency_key_is_tenant_scoped(repository, session, tenant_a, tenant_b, user):
    customer = await _create_customer(session, tenant_id=tenant_a.id)
    invoice = await _create_invoice(session, tenant_id=tenant_a.id, customer_id=customer.id, amount=Decimal("100.00"))
    payment = await _create_payment(
        session,
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        invoice_id=invoice.id,
        amount=Decimal("100.00"),
    )
    refund = Refund(
        id=uuid4(),
        tenant_id=tenant_a.id,
        payment_id=payment.id,
        amount=Decimal("20.00"),
        reason="duplicate charge",
        status=RefundStatus.REQUESTED,
        idempotency_key="refund-1",
        requested_by_user_id=user.id,
        executed_at=None,
        has_unknown_execution=False,
    )
    session.add(refund)
    await session.commit()

    result = await repository.get_refund_by_idempotency_key(
        scope=TenantScope(tenant_id=tenant_b.id),
        idempotency_key="refund-1",
    )

    assert result is None


@pytest.mark.asyncio
async def test_create_refund_request_returns_existing_row_for_same_idempotency_key(repository, session, tenant_a, user):
    customer = await _create_customer(session, tenant_id=tenant_a.id)
    invoice = await _create_invoice(session, tenant_id=tenant_a.id, customer_id=customer.id, amount=Decimal("100.00"))
    payment = await _create_payment(
        session,
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        invoice_id=invoice.id,
        amount=Decimal("100.00"),
    )
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=user.id, actor_type="user")

    created = await repository.create_refund_request(
        scope=scope,
        payment_id=payment.id,
        idempotency_key="refund-1",
        amount=Decimal("20.00"),
    )
    returned = await repository.create_refund_request(
        scope=scope,
        payment_id=payment.id,
        idempotency_key="refund-1",
        amount=Decimal("20.00"),
    )
    await session.commit()

    assert returned.id == created.id


@pytest.mark.asyncio
async def test_create_refund_request_rejects_amount_greater_than_payment(repository, session, tenant_a, user):
    customer = await _create_customer(session, tenant_id=tenant_a.id)
    invoice = await _create_invoice(session, tenant_id=tenant_a.id, customer_id=customer.id, amount=Decimal("100.00"))
    payment = await _create_payment(
        session,
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        invoice_id=invoice.id,
        amount=Decimal("100.00"),
    )

    with pytest.raises(DomainError, match="refund amount cannot exceed payment amount"):
        await repository.create_refund_request(
            scope=TenantScope(tenant_id=tenant_a.id, actor_id=user.id, actor_type="user"),
            payment_id=payment.id,
            idempotency_key="refund-too-large",
            amount=Decimal("120.00"),
        )


@pytest.mark.asyncio
async def test_create_refund_request_blocks_normal_retry_after_unknown_execution(repository, session, tenant_a, user):
    customer = await _create_customer(session, tenant_id=tenant_a.id)
    invoice = await _create_invoice(session, tenant_id=tenant_a.id, customer_id=customer.id, amount=Decimal("100.00"))
    payment = await _create_payment(
        session,
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        invoice_id=invoice.id,
        amount=Decimal("100.00"),
    )
    existing_refund = Refund(
        id=uuid4(),
        tenant_id=tenant_a.id,
        payment_id=payment.id,
        amount=Decimal("20.00"),
        reason="provider timeout",
        status=RefundStatus.UNKNOWN_EXECUTION_STATE,
        idempotency_key="refund-unknown",
        requested_by_user_id=user.id,
        executed_at=None,
        has_unknown_execution=True,
    )
    session.add(existing_refund)
    await session.commit()

    with pytest.raises(DomainError, match="unknown execution state refunds must be reconciled before retry"):
        await repository.create_refund_request(
            scope=TenantScope(tenant_id=tenant_a.id, actor_id=user.id, actor_type="user"),
            payment_id=payment.id,
            idempotency_key="refund-retry",
            amount=Decimal("20.00"),
        )


@pytest.mark.asyncio
async def test_cross_tenant_refund_payment_link_is_rejected(session, tenant_a, tenant_b, user):
    customer_a = await _create_customer(session, tenant_id=tenant_a.id)
    invoice_a = await _create_invoice(session, tenant_id=tenant_a.id, customer_id=customer_a.id, amount=Decimal("100.00"))
    payment_a = await _create_payment(
        session,
        tenant_id=tenant_a.id,
        customer_id=customer_a.id,
        invoice_id=invoice_a.id,
        amount=Decimal("100.00"),
    )
    await session.flush()

    session.add(
        Refund(
            id=uuid4(),
            tenant_id=tenant_b.id,
            payment_id=payment_a.id,
            amount=Decimal("10.00"),
            reason="cross tenant",
            status=RefundStatus.REQUESTED,
            idempotency_key="cross-tenant-refund",
            requested_by_user_id=user.id,
            executed_at=None,
            has_unknown_execution=False,
        )
    )

    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()
