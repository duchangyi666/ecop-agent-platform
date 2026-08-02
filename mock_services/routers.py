from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from mock_services.storage import (
    MockBillingStorage,
    MockCrmStorage,
    MockMonitoringStorage,
    MockNotificationStorage,
)


class RefundPreviewRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    payment_id: UUID
    amount: Decimal
    idempotency_key: str = Field(min_length=1, max_length=120)


class RefundExecuteRequest(RefundPreviewRequest):
    pass


class IncidentCreateRequest(BaseModel):
    service: str = Field(min_length=1, max_length=80)
    severity: str = Field(min_length=1, max_length=40)
    summary: str = Field(min_length=1, max_length=500)


class NotificationSendRequest(BaseModel):
    recipient: str = Field(min_length=1, max_length=160)
    channel: str = Field(min_length=1, max_length=40)
    message: str = Field(min_length=1, max_length=1000)


def create_billing_router(storage: MockBillingStorage) -> APIRouter:
    router = APIRouter(prefix="/billing", tags=["mock-billing"])

    @router.post("/refunds/preview")
    async def preview_refund(payload: RefundPreviewRequest):
        try:
            return storage.preview_refund(
                payment_id=payload.payment_id,
                amount=payload.amount,
                idempotency_key=payload.idempotency_key,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "payment_not_found"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_refund"}) from exc

    @router.post("/refunds", status_code=201)
    async def execute_refund(
        payload: RefundExecuteRequest,
        response: Response,
    ):
        try:
            result = storage.execute_refund(
                payment_id=payload.payment_id,
                amount=payload.amount,
                idempotency_key=payload.idempotency_key,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "payment_not_found"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_refund"}) from exc
        response.status_code = (
            status.HTTP_201_CREATED
            if result.get("created") is True
            else status.HTTP_200_OK
        )
        return result

    @router.get("/refunds/{idempotency_key}")
    async def get_refund(idempotency_key: str):
        refund = storage.get_refund(idempotency_key)
        if refund is None:
            raise HTTPException(status_code=404, detail={"code": "refund_not_found"})
        return refund

    return router


def create_crm_router(storage: MockCrmStorage) -> APIRouter:
    router = APIRouter(prefix="/crm", tags=["mock-crm"])

    @router.get("/customers/{customer_id}")
    async def get_customer(customer_id: UUID):
        customer = storage.get_customer(customer_id)
        if customer is None:
            raise HTTPException(status_code=404, detail={"code": "customer_not_found"})
        return customer

    return router


def create_monitoring_router(storage: MockMonitoringStorage) -> APIRouter:
    router = APIRouter(prefix="/monitoring", tags=["mock-monitoring"])

    @router.get("/incidents")
    async def list_incidents():
        return {"incidents": storage.list_incidents()}

    @router.post("/incidents", status_code=201)
    async def create_incident(payload: IncidentCreateRequest):
        return storage.add_incident(
            service=payload.service,
            severity=payload.severity,
            summary=payload.summary,
        )

    return router


def create_notification_router(storage: MockNotificationStorage) -> APIRouter:
    router = APIRouter(prefix="/notification", tags=["mock-notification"])

    @router.post("/notifications", status_code=202)
    async def send_notification(payload: NotificationSendRequest):
        return storage.send(
            recipient=payload.recipient,
            channel=payload.channel,
            message=payload.message,
        )

    @router.get("/notifications")
    async def list_notifications():
        return {"notifications": storage.list_notifications()}

    return router
