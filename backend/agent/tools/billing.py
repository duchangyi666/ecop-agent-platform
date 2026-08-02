from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.database.base import TenantScope
from backend.database.unit_of_work import UnitOfWork
from backend.domain.common import DomainError


class RefundToolRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: TenantScope
    payment_id: UUID
    idempotency_key: str
    amount: Decimal
    approved: bool = False


class RefundToolPreview(BaseModel):
    model_config = ConfigDict(frozen=True)

    payment_id: UUID
    amount: Decimal
    idempotency_key: str
    status: str


class BillingTool:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def preview(self, request: RefundToolRequest) -> RefundToolPreview:
        payment = await self.uow.billing.get_payment_for_tenant(
            scope=request.scope,
            payment_id=request.payment_id,
        )
        if payment is None:
            raise DomainError("payment not found in tenant scope")
        if request.amount <= Decimal("0.00") or request.amount > payment.amount:
            raise DomainError("refund amount is invalid")
        return RefundToolPreview(
            payment_id=payment.id,
            amount=request.amount,
            idempotency_key=request.idempotency_key,
            status="previewed",
        )

    async def execute(self, request: RefundToolRequest) -> Any:
        if not request.approved:
            raise DomainError("refund execution requires policy approval")
        return await self.request(request)

    async def request(self, request: RefundToolRequest) -> Any:
        return await self.uow.billing.create_refund_request(
            scope=request.scope,
            payment_id=request.payment_id,
            idempotency_key=request.idempotency_key,
            amount=request.amount,
        )


__all__ = ["BillingTool", "RefundToolPreview", "RefundToolRequest"]
