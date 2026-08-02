from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.database.base import TenantScope
from backend.database.base import Base
from backend.database.models.billing import Customer, Invoice, Payment, Refund
from backend.database.models.governance import RuntimeSpan, RuntimeTrace, ToolExecution, WorkflowCheckpoint
from backend.database.models.identity import Permission, Role, Tenant, User, UserRole
from backend.database.models.support import ApprovalAction, ApprovalRequest, AuditLog
from backend.domain.billing import PaymentStatus

TEST_DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations"


@pytest_asyncio.fixture
async def database_url() -> str:
    import backend.database.models  # noqa: F401

    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    async with engine.begin() as connection:
        tables = await connection.run_sync(lambda sync_connection: inspect(sync_connection).get_table_names())
        if "tenants" not in tables:
            await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    return TEST_DATABASE_URL


@pytest_asyncio.fixture
async def session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    import backend.database.models  # noqa: F401

    engine = create_async_engine(database_url, pool_pre_ping=True, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _cleanup(factory: async_sessionmaker[AsyncSession], tenant_id: UUID) -> None:
    async with factory() as session:
        for model in (
            WorkflowCheckpoint,
            RuntimeSpan,
            ToolExecution,
            AuditLog,
            ApprovalAction,
            ApprovalRequest,
            RuntimeTrace,
            Refund,
            Payment,
            Invoice,
            Customer,
            UserRole,
            Permission,
            Role,
            User,
        ):
            await session.execute(delete(model).where(model.tenant_id == tenant_id))
        await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        await session.commit()


@pytest_asyncio.fixture
async def tenant_a(session_factory: async_sessionmaker[AsyncSession]):
    tenant = Tenant(
        id=uuid4(),
        slug=f"task7-tenant-a-{uuid4().hex[:8]}",
        name="Task 7 Tenant A",
        status="active",
    )
    async with session_factory() as session:
        session.add(tenant)
        await session.commit()
    try:
        yield tenant
    finally:
        await _cleanup(session_factory, tenant.id)


@pytest_asyncio.fixture
async def tenant_b(session_factory: async_sessionmaker[AsyncSession]):
    tenant = Tenant(
        id=uuid4(),
        slug=f"task7-tenant-b-{uuid4().hex[:8]}",
        name="Task 7 Tenant B",
        status="active",
    )
    async with session_factory() as session:
        session.add(tenant)
        await session.commit()
    try:
        yield tenant
    finally:
        await _cleanup(session_factory, tenant.id)


@pytest_asyncio.fixture
async def tenant_a_user(session_factory: async_sessionmaker[AsyncSession], tenant_a: Tenant) -> User:
    user = User(
        id=uuid4(),
        tenant_id=tenant_a.id,
        email=f"task7-a-{uuid4().hex[:8]}@example.com",
        display_name="Task 7 Agent A",
        status="active",
        last_login_at=None,
    )
    async with session_factory() as session:
        session.add(user)
        await session.commit()
    return user


@pytest_asyncio.fixture
async def customer_id(session_factory: async_sessionmaker[AsyncSession], tenant_a: Tenant) -> UUID:
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant_a.id,
        name="Task 7 Customer",
        external_customer_id=f"task7-cust-{uuid4().hex[:8]}",
        support_tier="standard",
        status="active",
    )
    async with session_factory() as session:
        session.add(customer)
        await session.commit()
    return customer.id


@pytest_asyncio.fixture
async def payment(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_a: Tenant,
    customer_id: UUID,
) -> Payment:
    invoice = Invoice(
        id=uuid4(),
        tenant_id=tenant_a.id,
        customer_id=customer_id,
        subscription_id=None,
        external_invoice_id=f"task7-invoice-{uuid4().hex[:8]}",
        amount=Decimal("88.00"),
        currency="CNY",
        status="issued",
        issued_at=datetime.now(timezone.utc),
    )
    payment = Payment(
        id=uuid4(),
        tenant_id=tenant_a.id,
        customer_id=customer_id,
        invoice_id=invoice.id,
        external_payment_id=f"task7-pay-{uuid4().hex[:8]}",
        amount=Decimal("88.00"),
        currency="CNY",
        status=PaymentStatus.SUCCEEDED,
        paid_at=datetime.now(timezone.utc),
    )
    async with session_factory() as session:
        session.add(invoice)
        session.add(payment)
        await session.commit()
    return payment


@pytest_asyncio.fixture
async def uow(session_factory: async_sessionmaker[AsyncSession], tenant_a: Tenant, tenant_a_user: User):
    from backend.database.unit_of_work import UnitOfWork

    active_uow = UnitOfWork(
        session_factory=session_factory,
        scope=TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user"),
    )
    try:
        yield active_uow
    finally:
        await active_uow.session.close()
