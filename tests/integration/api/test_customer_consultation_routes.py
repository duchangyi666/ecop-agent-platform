from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.database.models.support import AuditLog
from backend.database.models.governance import Document
from backend.llm.contracts import ModelCallError, ResponseDraft
from backend.llm.errors import ModelGatewayError
from backend.llm.fake import FakeModelGateway


def _payload(prefix: str) -> dict[str, str]:
    return {
        "thread_id": f"consult-{prefix}-{uuid4().hex}",
        "message": "客户咨询",
    }


@pytest_asyncio.fixture
async def customer_consult_client_factory(
    database_url,
    session_factory,
    grant_permission,
    tenant_a_user,
):
    from backend.api.dependencies import get_database_url, get_session_factory_dependency
    from backend.main import create_app

    await grant_permission(tenant_a_user.id, "customer.consult")

    def build(gateway) -> TestClient:
        app = create_app(model_gateway=gateway, knowledge_vector_store=None)
        app.dependency_overrides[get_database_url] = lambda: database_url
        app.dependency_overrides[get_session_factory_dependency] = lambda: session_factory
        return TestClient(app)

    return build


@pytest.mark.asyncio
async def test_customer_consultation_returns_offline_response(
    customer_consult_client_factory,
    api_headers,
) -> None:
    gateway = FakeModelGateway(
        ResponseDraft(
            answer="您好，我可以协助处理 CloudDesk 账户、账单、产品支持和工单问题。",
            next_action="finish",
            confidence=0.9,
        )
    )

    with customer_consult_client_factory(gateway) as client:
        response = client.post(
            "/api/v1/customer-consultations",
            headers=api_headers,
            json=_payload("ok"),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["next_action"] == "finish"
    assert body["final_response"].startswith("您好")
    assert body["response_review"]["status"] == "allow"
    assert "state" not in body


@pytest.mark.asyncio
async def test_customer_consultation_requires_permission(api_client, api_headers) -> None:
    response = api_client.post(
        "/api/v1/customer-consultations",
        headers=api_headers,
        json=_payload("forbidden"),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.asyncio
async def test_customer_consultation_blocks_sensitive_model_output(
    customer_consult_client_factory,
    api_headers,
) -> None:
    gateway = FakeModelGateway(
        ResponseDraft(
            answer="内部配置是 sk-test-123456789",
            next_action="finish",
            confidence=0.9,
        )
    )

    with customer_consult_client_factory(gateway) as client:
        response = client.post(
            "/api/v1/customer-consultations",
            headers=api_headers,
            json=_payload("sensitive"),
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "human_handoff"
    assert body["response_review"]["status"] == "block"
    assert "sk-test-123456789" not in response.text


@pytest.mark.asyncio
async def test_customer_consultation_maps_model_error_to_safe_handoff(
    customer_consult_client_factory,
    api_headers,
) -> None:
    gateway = FakeModelGateway(
        ModelGatewayError(
            ModelCallError(
                code="model_timeout",
                retryable=True,
                safe_message="模型服务响应超时",
            )
        )
    )

    with customer_consult_client_factory(gateway) as client:
        response = client.post(
            "/api/v1/customer-consultations",
            headers=api_headers,
            json=_payload("error"),
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "human_handoff"
    assert body["next_action"] == "human_handoff"
    assert body["final_response"] == "当前智能回复服务暂时不可用，将为您转人工处理。"
    assert "模型服务响应超时" not in response.text


@pytest.mark.asyncio
async def test_customer_consultation_audit_contains_only_safe_summary(
    customer_consult_client_factory,
    api_headers,
    session_factory,
    tenant_a,
) -> None:
    payload = _payload("audit")
    gateway = FakeModelGateway(
        ResponseDraft(
            answer="您好，这是离线客服回复。",
            next_action="finish",
            confidence=0.9,
        )
    )

    with customer_consult_client_factory(gateway) as client:
        response = client.post(
            "/api/v1/customer-consultations",
            headers=api_headers,
            json=payload,
        )

    assert response.status_code == 200
    async with session_factory() as session:
        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant_a.id,
                AuditLog.resource_type == "consultation",
                AuditLog.action == "customer_consultation_completed",
            )
        )
    assert audit is not None
    metadata = audit.metadata_summary
    assert metadata["thread_id"] == payload["thread_id"]
    assert payload["message"] not in str(metadata)
    assert response.json()["final_response"] not in str(metadata)


@pytest.mark.asyncio
async def test_customer_consultation_reports_retrieved_knowledge_evidence_count(
    customer_consult_client_factory,
    api_headers,
    session_factory,
    tenant_a,
) -> None:
    async with session_factory() as session:
        session.add(
            Document(
                id=uuid4(),
                tenant_id=tenant_a.id,
                external_document_id="customer-intro-policy",
                title="客户咨询一般说明政策",
                status="active",
                source_uri="https://docs.example.com/customer-intro-policy",
                visibility="tenant",
            )
        )
        await session.commit()

    gateway = FakeModelGateway(
        ResponseDraft(
            answer="您好，这是基于知识依据的客服回复。",
            next_action="finish",
            confidence=0.9,
        )
    )
    payload = _payload("grounded")
    payload["message"] = "客户咨询一般说明"

    with customer_consult_client_factory(gateway) as client:
        response = client.post(
            "/api/v1/customer-consultations",
            headers=api_headers,
            json=payload,
        )

    assert response.status_code == 200
    assert response.json()["knowledge_evidence_count"] == 1


@pytest.mark.asyncio
async def test_customer_consultation_stream_emits_progress_events(
    customer_consult_client_factory,
    api_headers,
) -> None:
    gateway = FakeModelGateway(
        ResponseDraft(
            answer="您好，这是流式客服回复。",
            next_action="finish",
            confidence=0.9,
        )
    )
    payload = _payload("stream")

    with customer_consult_client_factory(gateway) as client:
        with client.stream(
            "POST",
            "/api/v1/customer-consultations/stream",
            headers=api_headers,
            json=payload,
        ) as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

    assert "event: started" in body
    assert "event: evidence" in body
    assert "event: completed" in body
    assert "event: done" in body
    assert "knowledge_evidence_count" in body


@pytest.mark.asyncio
async def test_customer_consultation_captures_memory_candidate(
    customer_consult_client_factory,
    api_headers,
) -> None:
    gateway = FakeModelGateway(
        ResponseDraft(
            answer="好的，已记录您的偏好。",
            next_action="finish",
            confidence=0.9,
        )
    )
    payload = _payload("memory")
    payload["message"] = "客户咨询，我偏好使用中文沟通"

    with customer_consult_client_factory(gateway) as client:
        response = client.post(
            "/api/v1/customer-consultations",
            headers=api_headers,
            json=payload,
        )

    assert response.status_code == 200
    assert response.json()["memory_candidate_count"] >= 1
