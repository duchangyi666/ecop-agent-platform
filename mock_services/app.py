from __future__ import annotations

from fastapi import FastAPI

from mock_services.routers import (
    create_billing_router,
    create_crm_router,
    create_monitoring_router,
    create_notification_router,
)
from mock_services.storage import (
    MockBillingStorage,
    MockCrmStorage,
    MockMonitoringStorage,
    MockNotificationStorage,
)


def create_mock_services_app(
    *,
    billing_storage: MockBillingStorage | None = None,
    crm_storage: MockCrmStorage | None = None,
    monitoring_storage: MockMonitoringStorage | None = None,
    notification_storage: MockNotificationStorage | None = None,
) -> FastAPI:
    app = FastAPI(title="CloudDesk Mock Services", version="0.1.0")
    app.include_router(create_billing_router(billing_storage or MockBillingStorage()))
    app.include_router(create_crm_router(crm_storage or MockCrmStorage()))
    app.include_router(create_monitoring_router(monitoring_storage or MockMonitoringStorage()))
    app.include_router(create_notification_router(notification_storage or MockNotificationStorage()))
    return app


mock_services_app = create_mock_services_app()


__all__ = ["create_mock_services_app", "mock_services_app"]
