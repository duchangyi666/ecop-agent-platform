from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.base import TenantScope
from backend.database.models.billing import Payment, Refund
from backend.database.repositories.base import TenantScopedRepository
from backend.domain.billing import PaymentStatus, RefundStatus
from backend.domain.common import DomainError, ensure_money, ensure_utc


class BillingRepository(TenantScopedRepository):
    DUPLICATE_CHARGE_WINDOW = timedelta(minutes=5)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_payment_for_tenant(
        self, *, scope: TenantScope, payment_id: UUID, for_update: bool = False,
    ) -> Payment | None:
        statement = self._tenant_visible(select(Payment), Payment, scope=scope).where(Payment.id == payment_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return await self.session.scalar(statement)

    async def find_duplicate_charge(
        self,
        *,
        scope: TenantScope,
        customer_id: UUID,
        amount: Decimal,
        occurred_at: datetime,
    ) -> list[Payment]:
        ensured_amount = ensure_money(amount)
        ensured_occurred_at = ensure_utc(occurred_at)
        window_start = ensured_occurred_at - self.DUPLICATE_CHARGE_WINDOW
        window_end = ensured_occurred_at + self.DUPLICATE_CHARGE_WINDOW

        statement = self._tenant_visible(select(Payment), Payment, scope=scope).where(
            Payment.customer_id == customer_id,
            Payment.amount == ensured_amount,
            Payment.paid_at >= window_start,
            Payment.paid_at <= window_end,
        )
        result = await self.session.scalars(statement.order_by(Payment.paid_at))
        return list(result.all())

    async def get_refund_by_idempotency_key(self, *, scope: TenantScope, idempotency_key: str) -> Refund | None:
        statement = self._tenant_visible(select(Refund), Refund, scope=scope).where(Refund.idempotency_key == idempotency_key)
        return await self.session.scalar(statement)

    async def list_recent_payments(
        self,
        *,
        scope: TenantScope,
        customer_id: UUID,
        limit: int = 5,
    ) -> list[Payment]:
        statement = self._tenant_visible(select(Payment), Payment, scope=scope).where(
            Payment.customer_id == customer_id,
            Payment.status == PaymentStatus.SUCCEEDED,
        )
        result = await self.session.scalars(statement.order_by(Payment.paid_at.desc()).limit(limit))
        return list(result.all())

    async def list_refunds_for_customer(
        self,
        *,
        scope: TenantScope,
        customer_id: UUID,
        limit: int = 5,
    ) -> list[Refund]:
        statement = (
            self._tenant_visible(select(Refund), Refund, scope=scope)
            .join(Payment, Payment.id == Refund.payment_id)
            .where(Payment.customer_id == customer_id, Payment.deleted_at.is_(None))
        )
        result = await self.session.scalars(statement.order_by(Refund.created_at.desc()).limit(limit))
        return list(result.all())

    async def create_refund_request(
        self,
        *,
        scope: TenantScope,
        payment_id: UUID,
        idempotency_key: str,
        amount: Decimal,
    ) -> Refund:
        existing = await self.get_refund_by_idempotency_key(scope=scope, idempotency_key=idempotency_key)
        if existing is not None:
            return existing

        payment = await self.get_payment_for_tenant(scope=scope, payment_id=payment_id)
        if payment is None:
            raise DomainError("payment not found in tenant scope")

        ensured_amount = ensure_money(amount)
        if ensured_amount > payment.amount:
            raise DomainError("refund amount cannot exceed payment amount")

        unknown_statement = self._tenant_visible(select(Refund), Refund, scope=scope).where(
            Refund.payment_id == payment_id,
            (Refund.has_unknown_execution.is_(True)) | (Refund.status == RefundStatus.UNKNOWN_EXECUTION_STATE),
        )
        unknown_refund = await self.session.scalar(unknown_statement.limit(1))
        if unknown_refund is not None:
            raise DomainError("unknown execution state refunds must be reconciled before retry")

        refund = Refund(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            payment_id=payment_id,
            amount=ensured_amount,
            reason="refund requested",
            status=RefundStatus.REQUESTED,
            idempotency_key=idempotency_key,
            requested_by_user_id=scope.actor_id,
            executed_at=None,
            has_unknown_execution=False,
        )
        self.session.add(refund)
        await self.session.flush()
        return refund


__all__ = ["BillingRepository"]
