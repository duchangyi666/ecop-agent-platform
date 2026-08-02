from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from backend.database.base import TenantScope
from backend.database.models.governance import AgentDefinition
from backend.database.repositories.governance import GovernanceRepository


async def _seed_runtime_data(session_factory, tenant_id) -> dict:
    async with session_factory() as session:
        session.add(
            AgentDefinition(
                id=uuid4(),
                tenant_id=tenant_id,
                agent_code="customer_service",
                name="Customer Service",
                status="active",
            )
        )
        governance = GovernanceRepository(session)
        trace = await governance.create_runtime_trace(
            scope=TenantScope(tenant_id=tenant_id),
            trace_key="runtime-api",
            entrypoint="agent.customer_consultation",
            input_summary="masked",
            input_hash="hash",
        )
        trace.total_input_tokens = 10
        trace.total_output_tokens = 5
        trace.total_cost = Decimal("0.01")
        await governance.complete_runtime_trace(
            trace_id=trace.id,
            status="completed",
            error_summary=None,
        )
        await session.commit()
        return {"trace_id": trace.id}


@pytest.mark.asyncio
async def test_runtime_routes_return_traces_cost_and_agents(
    runtime_api_client,
    api_headers,
    session_factory,
    tenant_a,
) -> None:
    seeded = await _seed_runtime_data(session_factory, tenant_a.id)

    traces_response = runtime_api_client.get(
        "/api/v1/runtime/traces",
        headers=api_headers,
    )
    cost_response = runtime_api_client.get(
        "/api/v1/runtime/costs",
        headers=api_headers,
    )
    agents_response = runtime_api_client.get(
        "/api/v1/runtime/agents",
        headers=api_headers,
    )
    detail_response = runtime_api_client.get(
        f"/api/v1/runtime/traces/{seeded['trace_id']}",
        headers=api_headers,
    )

    assert traces_response.status_code == 200
    assert len(traces_response.json()["traces"]) == 1
    assert cost_response.status_code == 200
    assert cost_response.json()["trace_count"] == 1
    assert agents_response.status_code == 200
    assert agents_response.json()["agents"][0]["agent_code"] == "customer_service"
    assert detail_response.status_code == 200
    assert detail_response.json()["trace"]["trace_id"] == str(seeded["trace_id"])


@pytest.mark.asyncio
async def test_runtime_routes_require_permission(api_client, api_headers) -> None:
    response = api_client.get(
        "/api/v1/runtime/traces",
        headers=api_headers,
    )

    assert response.status_code == 403
