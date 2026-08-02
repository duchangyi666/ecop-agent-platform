from __future__ import annotations

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from uuid import uuid4

from backend.database.models.identity import Permission, Role, UserRole
from backend.llm.contracts import ResponseDraft
from backend.llm.fake import FakeModelGateway
pytest_plugins = ("tests.integration.database.conftest",)


@pytest_asyncio.fixture
def model_gateway():
    return FakeModelGateway(
        ResponseDraft(
            answer="您好，我可以协助处理 CloudDesk 账户、账单、产品支持和工单问题。",
            next_action="finish",
            confidence=0.9,
        )
    )


@pytest_asyncio.fixture
async def session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, pool_pre_ping=True, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def api_client(database_url: str, session_factory, model_gateway):
    from backend.api.dependencies import get_database_url, get_session_factory_dependency
    from backend.main import create_app

    app = create_app(model_gateway=model_gateway, knowledge_vector_store=None)
    app.dependency_overrides[get_database_url] = lambda: database_url
    app.dependency_overrides[get_session_factory_dependency] = lambda: session_factory
    with TestClient(app) as client:
        yield client


@pytest_asyncio.fixture
async def api_headers(tenant_a, tenant_a_user) -> dict[str, str]:
    return {
        "X-Tenant-Id": str(tenant_a.id),
        "X-Actor-Id": str(tenant_a_user.id),
        "X-Actor-Type": "user",
    }


@pytest_asyncio.fixture
async def grant_permission(session_factory, tenant_a):
    async def grant(user_id, permission_code: str, *, permission_status: str = "active", role_status: str = "active") -> None:
        role_id = uuid4()
        permission_id = uuid4()
        async with session_factory() as session:
            session.add(
                Role(
                    id=role_id,
                    tenant_id=tenant_a.id,
                    code=f"role-{permission_code.replace('.', '-')}-{uuid4().hex[:8]}",
                    name=permission_code,
                    status=role_status,
                    is_platform_role=False,
                )
            )
            session.add(
                Permission(
                    id=permission_id,
                    tenant_id=tenant_a.id,
                    role_id=role_id,
                    code=permission_code,
                    name=permission_code,
                    status=permission_status,
                )
            )
            session.add(UserRole(id=uuid4(), tenant_id=tenant_a.id, user_id=user_id, role_id=role_id))
            await session.commit()

    return grant


@pytest_asyncio.fixture
async def authorized_api_client(api_client, grant_permission, tenant_a_user):
    await grant_permission(tenant_a_user.id, "refund.request")
    await grant_permission(tenant_a_user.id, "refund.approve")
    return api_client


@pytest_asyncio.fixture
async def customer_consult_api_client(api_client, grant_permission, tenant_a_user):
    await grant_permission(tenant_a_user.id, "customer.consult")
    return api_client


@pytest_asyncio.fixture
async def ticket_api_client(api_client, grant_permission, tenant_a_user):
    await grant_permission(tenant_a_user.id, "ticket.create")
    return api_client


@pytest_asyncio.fixture
async def ticket_ops_api_client(api_client, grant_permission, tenant_a_user):
    await grant_permission(tenant_a_user.id, "ticket.create")
    await grant_permission(tenant_a_user.id, "ticket.read")
    await grant_permission(tenant_a_user.id, "ticket.update")
    return api_client


@pytest_asyncio.fixture
async def knowledge_api_client(api_client, grant_permission, tenant_a_user):
    await grant_permission(tenant_a_user.id, "knowledge.search")
    return api_client


@pytest_asyncio.fixture
async def knowledge_ops_api_client(api_client, grant_permission, tenant_a_user):
    await grant_permission(tenant_a_user.id, "knowledge.search")
    await grant_permission(tenant_a_user.id, "knowledge.ingest")
    await grant_permission(tenant_a_user.id, "knowledge.delete")
    return api_client


@pytest_asyncio.fixture
async def knowledge_ingest_api_client(api_client, grant_permission, tenant_a_user):
    await grant_permission(tenant_a_user.id, "knowledge.search")
    await grant_permission(tenant_a_user.id, "knowledge.ingest")
    return api_client


@pytest_asyncio.fixture
async def conversation_api_client(api_client, grant_permission, tenant_a_user):
    await grant_permission(tenant_a_user.id, "conversation.create")
    await grant_permission(tenant_a_user.id, "conversation.read")
    await grant_permission(tenant_a_user.id, "conversation.write")
    return api_client


@pytest_asyncio.fixture
async def approval_read_api_client(api_client, grant_permission, tenant_a_user):
    await grant_permission(tenant_a_user.id, "approval.read")
    return api_client


@pytest_asyncio.fixture
async def evaluation_api_client(api_client, grant_permission, tenant_a_user):
    await grant_permission(tenant_a_user.id, "evaluation.read")
    await grant_permission(tenant_a_user.id, "evaluation.run")
    return api_client


@pytest_asyncio.fixture
async def runtime_api_client(api_client, grant_permission, tenant_a_user):
    await grant_permission(tenant_a_user.id, "runtime.read")
    return api_client


@pytest_asyncio.fixture
async def request_only_api_client(api_client, grant_permission, tenant_a_user):
    await grant_permission(tenant_a_user.id, "refund.request")
    return api_client
