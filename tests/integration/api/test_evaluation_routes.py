from __future__ import annotations

from uuid import uuid4

import pytest

from backend.database.base import TenantScope
from backend.database.models.governance import Document
from backend.database.repositories.evaluation import EvaluationRepository


async def _seed_evaluation_data(session_factory, tenant_id) -> None:
    document = Document(
        id=uuid4(),
        tenant_id=tenant_id,
        external_document_id="eval-refund-policy",
        title="退款政策",
        status="active",
        source_uri="https://docs.example.com/eval-refund-policy",
        visibility="tenant",
    )
    async with session_factory() as session:
        session.add(document)
        await session.commit()
        scope = TenantScope(tenant_id=tenant_id)
        repository = EvaluationRepository(session)
        dataset = await repository.create_dataset(
            scope=scope,
            dataset_code="api-retrieval-demo",
            name="API Retrieval Demo",
        )
        await repository.create_case(
            scope=scope,
            dataset_id=dataset.id,
            case_key="refund",
            input_summary="退款",
            expected_summary={"document_ids": [str(document.id)]},
            tags=["retrieval"],
        )
        await session.commit()


@pytest.mark.asyncio
async def test_evaluation_run_and_list_routes(
    evaluation_api_client,
    api_headers,
    session_factory,
    tenant_a,
) -> None:
    await _seed_evaluation_data(session_factory, tenant_a.id)

    run_response = evaluation_api_client.post(
        "/api/v1/evaluations/run",
        headers=api_headers,
        json={
            "dataset_code": "api-retrieval-demo",
            "limit": 5,
        },
    )

    assert run_response.status_code == 200, run_response.text
    run_body = run_response.json()
    assert run_body["case_count"] == 1
    assert run_body["metrics"]["recall_at_k"] > 0

    list_response = evaluation_api_client.get(
        "/api/v1/evaluations",
        headers=api_headers,
    )

    assert list_response.status_code == 200
    assert len(list_response.json()["runs"]) == 1


@pytest.mark.asyncio
async def test_evaluation_routes_require_permission(api_client, api_headers) -> None:
    response = api_client.get("/api/v1/evaluations", headers=api_headers)

    assert response.status_code == 403
