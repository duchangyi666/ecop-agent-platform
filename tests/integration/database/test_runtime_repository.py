from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from backend.database.base import TenantScope
from backend.database.models.governance import AgentDefinition
from backend.database.repositories.governance import GovernanceRepository
from backend.database.repositories.runtime import RuntimeRepository


@pytest.mark.asyncio
async def test_runtime_repository_lists_traces_spans_cost_and_agents(
    session_factory,
    tenant_a,
) -> None:
    scope = TenantScope(tenant_id=tenant_a.id)
    async with session_factory() as session:
        agent = AgentDefinition(
            id=uuid4(),
            tenant_id=tenant_a.id,
            agent_code="customer_service",
            name="Customer Service",
            status="active",
        )
        session.add(agent)
        governance = GovernanceRepository(session)
        trace = await governance.create_runtime_trace(
            scope=scope,
            trace_key="runtime-api-test",
            entrypoint="agent.customer_consultation",
            input_summary="masked",
            input_hash="hash",
        )
        trace.total_input_tokens = 100
        trace.total_output_tokens = 50
        trace.total_cost = Decimal("0.03")
        await governance.complete_runtime_trace(
            trace_id=trace.id,
            status="completed",
            error_summary=None,
            total_input_tokens=120,
            total_output_tokens=60,
        )
        await governance.record_runtime_span(
            trace_id=trace.id,
            node_name="retrieve_context",
            status="ok",
            input_summary="query digest",
            output_summary="2 docs",
        )
        await session.commit()

        repository = RuntimeRepository(session)
        traces = await repository.list_traces(scope=scope)
        detail = await repository.get_trace(scope=scope, trace_id=trace.id)
        spans = await repository.list_spans(scope=scope, trace_id=trace.id)
        summary = await repository.summary(scope=scope)
        agents = await repository.list_agents(scope=scope)

    assert len(traces) == 1
    assert detail is not None
    assert len(spans) == 1
    assert summary["trace_count"] == 1
    assert summary["total_input_tokens"] == 120
    assert summary["total_output_tokens"] == 60
    assert summary["total_cost"] == "0.03"
    assert [item.agent_code for item in agents] == ["customer_service"]
