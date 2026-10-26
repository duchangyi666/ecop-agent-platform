from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.database.models.billing import Customer, CustomerContact, Payment
from backend.database.models.governance import Document, DocumentVersion, RuntimeTrace
from backend.database.models.support import Ticket
from scripts.seed_demo_scenario import seed_demo_scenario


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ("oidc", "jwt-only"))
async def test_demo_scenario_rejects_non_development_modes(monkeypatch, mode) -> None:
    monkeypatch.setenv("AUTH_MODE", mode)
    with pytest.raises(ValueError, match="AUTH_MODE=dev"):
        await seed_demo_scenario(database_url="invalid-url")


@pytest.mark.asyncio
async def test_demo_scenario_reuses_business_objects_and_knowledge_versions(
    database_url, session_factory, tenant_a, monkeypatch,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    first = await seed_demo_scenario(database_url=database_url, tenant_slug=tenant_a.slug)

    async def counts():
        async with session_factory() as session:
            return [await session.scalar(
                select(func.count()).select_from(model).where(model.tenant_id == tenant_a.id)
            ) for model in (
                Customer, CustomerContact, Payment, Ticket, Document, DocumentVersion, RuntimeTrace,
            )]

    before = await counts()
    second = await seed_demo_scenario(database_url=database_url, tenant_slug=tenant_a.slug)
    assert first == second
    assert before == await counts()
    assert before == [1, 1, 1, 1, 3, 3, 3]


@pytest.mark.asyncio
async def test_demo_scenario_supports_authenticated_business_walkthrough(
    database_url, tenant_a, api_client, monkeypatch,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("JWT_SECRET", "demo-test-secret-0123456789abcdef0123456789")
    scenario = await seed_demo_scenario(database_url=database_url, tenant_slug=tenant_a.slug)
    identities = {item["profile"]: item for item in scenario["identities"]}

    def login(profile):
        identity = identities[profile]
        response = api_client.post("/api/v1/auth/tokens", json={
            "tenant_id": identity["tenant_id"], "user_id": identity["user_id"],
        })
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    customer, agent, finance, guest = (
        login(profile) for profile in ("customer", "support_agent", "finance_reviewer", "guest")
    )
    knowledge = api_client.get(
        "/api/v1/knowledge/search", headers=customer, params={"q": "退款"},
    )
    assert knowledge.status_code == 200, knowledge.text
    assert knowledge.json()["results"]

    consultation = api_client.post("/api/v1/customer-consultations", headers=customer, json={
        "thread_id": f"demo-consult-{uuid4().hex}", "message": "企业版 SLA 与支持等级",
    })
    assert consultation.status_code == 200, consultation.text
    assert consultation.json()["knowledge_evidence_count"] >= 1

    stream = api_client.post("/api/v1/customer-consultations/stream", headers=customer, json={
        "thread_id": f"demo-stream-{uuid4().hex}", "message": "企业版 SLA 与支持等级",
    })
    assert stream.status_code == 200
    assert "event: completed" in stream.text and "event: done" in stream.text

    ticket = api_client.post("/api/v1/tickets", headers=agent, json={
        "thread_id": f"demo-ticket-{uuid4().hex}", "customer_id": scenario["customer_id"],
        "subject": "登录故障", "description_summary": "演示客户无法登录",
        "message": "请创建工单处理登录故障", "priority": "high",
    })
    assert ticket.status_code == 201, ticket.text

    thread_id = f"demo-refund-{uuid4().hex}"
    refund_payload = {
        "thread_id": thread_id, "payment_id": scenario["payment_id"], "amount": "1280.00",
        "refund_idempotency_key": f"demo-refund-{uuid4().hex}", "message": "申请退款",
    }
    denied = api_client.post("/api/v1/refunds", headers=guest, json=refund_payload)
    assert denied.status_code == 403
    refund = api_client.post("/api/v1/refunds", headers=finance, json=refund_payload)
    assert refund.status_code == 202, refund.text
    approval_url = f"/api/v1/approvals/{refund.json()['approval_request_id']}"
    denied_approval = api_client.post(approval_url, headers=customer, json={
        "thread_id": thread_id, "approved": True, "reason": "演示核验通过",
    })
    assert denied_approval.status_code == 403
    approved = api_client.post(approval_url, headers=finance, json={
        "thread_id": thread_id, "approved": True, "reason": "演示核验通过",
    })
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved_for_execution"

    traces = api_client.get("/api/v1/runtime/traces", headers=login("platform_admin"))
    assert traces.status_code == 200
    assert traces.json()["traces"]
