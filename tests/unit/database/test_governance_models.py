from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.database.base import Base, TenantScope
from tests.unit.database.helpers import find_constraint


@pytest.fixture
def repository(session):
    from backend.database.repositories.governance import GovernanceRepository

    return GovernanceRepository(session)


@pytest.fixture
async def customer(session, tenant_a):
    from backend.database.models.billing import Customer

    customer = Customer(
        id=uuid4(),
        tenant_id=tenant_a.id,
        name="Acme Corp",
        external_customer_id="cust-acme",
        support_tier="gold",
        status="active",
    )
    session.add(customer)
    await session.commit()
    return customer


def test_policy_version_has_effective_window() -> None:
    from backend.database.models.governance import PolicyVersion

    columns = PolicyVersion.__table__.c
    assert columns.effective_from is not None
    assert columns.effective_to is not None
    assert columns.effective_from.type.timezone is True
    assert columns.effective_to.type.timezone is True


def test_memory_record_has_ttl_and_confidence() -> None:
    from backend.database.models.governance import MemoryRecord

    columns = MemoryRecord.__table__.c
    assert columns.ttl_expires_at is not None
    assert columns.confidence is not None
    assert columns.ttl_expires_at.type.timezone is True


def test_runtime_trace_does_not_require_raw_prompt_column() -> None:
    from backend.database.models.governance import RuntimeTrace

    assert "raw_prompt" not in RuntimeTrace.__table__.c


def test_runtime_cost_uses_decimal_precision() -> None:
    from backend.database.models.governance import RuntimeTrace

    total_cost_column = RuntimeTrace.__table__.c.total_cost
    assert total_cost_column.type.asdecimal is True
    assert total_cost_column.type.precision == 18
    assert total_cost_column.type.scale == 2


def test_memory_record_customer_uses_tenant_scoped_foreign_key(metadata) -> None:
    constraint = find_constraint(
        "memory_records",
        "fk_memory_records_tenant_customer",
        metadata,
    )
    assert constraint is not None


def test_runtime_span_trace_uses_tenant_scoped_foreign_key(metadata) -> None:
    constraint = find_constraint(
        "runtime_spans",
        "fk_runtime_spans_tenant_trace",
        metadata,
    )
    assert constraint is not None


def test_governance_models_are_registered_on_shared_metadata() -> None:
    assert Base.metadata.tables["policies"] is not None
    assert Base.metadata.tables["policy_versions"] is not None
    assert Base.metadata.tables["memory_records"] is not None
    assert Base.metadata.tables["runtime_traces"] is not None
    assert Base.metadata.tables["evaluation_results"] is not None


@pytest.mark.asyncio
async def test_get_published_policy_returns_current_tenant_version(repository, tenant_a, tenant_b):
    from backend.database.models.governance import Policy, PolicyVersion

    now = datetime.now(timezone.utc)
    policy = Policy(
        id=uuid4(),
        tenant_id=tenant_a.id,
        policy_code="refund-governance",
        name="Refund Governance",
        status="active",
        owner_team="risk",
    )
    repository.session.add(policy)
    repository.session.add(
        PolicyVersion(
            id=uuid4(),
            tenant_id=tenant_a.id,
            policy_id=policy.id,
            version_number=1,
            status="published",
            content_summary={"rules": 1},
            content_hash="hash-v1",
            source_uri="s3://policies/refund-governance/v1.md",
            effective_from=now - timedelta(days=3),
            effective_to=now - timedelta(days=1),
            published_at=now - timedelta(days=3),
        )
    )
    current_version = PolicyVersion(
        id=uuid4(),
        tenant_id=tenant_a.id,
        policy_id=policy.id,
        version_number=2,
        status="published",
        content_summary={"rules": 2},
        content_hash="hash-v2",
        source_uri="s3://policies/refund-governance/v2.md",
        effective_from=now - timedelta(hours=2),
        effective_to=None,
        published_at=now - timedelta(hours=2),
    )
    repository.session.add(current_version)
    repository.session.add(
        Policy(
            id=uuid4(),
            tenant_id=tenant_b.id,
            policy_code="refund-governance",
            name="Other Tenant Refund Governance",
            status="active",
            owner_team="risk",
        )
    )
    await repository.session.commit()

    version = await repository.get_published_policy(
        scope=TenantScope(tenant_id=tenant_a.id),
        policy_code="refund-governance",
        at=now,
    )

    assert version is not None
    assert version.id == current_version.id
    assert version.tenant_id == tenant_a.id


@pytest.mark.asyncio
async def test_add_memory_candidate_redacts_sensitive_payload_and_tracks_hash(repository, tenant_a, customer):
    record = await repository.add_memory_candidate(
        scope=TenantScope(tenant_id=tenant_a.id),
        user_id=None,
        customer_id=customer.id,
        payload={
            "memory_type": "meeting_note",
            "content": "Customer asked for weekend support.",
            "prompt": "never persist raw prompt",
            "channel": "chat",
            "confidence": 0.85,
            "ttl_days": 30,
        },
    )

    assert record.tenant_id == tenant_a.id
    assert record.customer_id == customer.id
    assert record.payload_summary["prompt"] == "[REDACTED]"
    assert record.payload_summary["content"] == "Customer asked for weekend support."
    assert record.payload_hash
    assert record.confidence == 0.85
    assert record.ttl_expires_at is not None


@pytest.mark.asyncio
async def test_record_runtime_span_persists_summaries_without_raw_prompt(repository, tenant_a):
    from backend.database.models.governance import RuntimeTrace

    trace = RuntimeTrace(
        id=uuid4(),
        tenant_id=tenant_a.id,
        trace_key="trace-001",
        status="running",
        entrypoint="agent.workflow",
        input_summary="masked user request",
        input_hash="trace-input-hash",
        model_profile_version_id=None,
        prompt_version_id=None,
        total_input_tokens=0,
        total_output_tokens=0,
        total_cost=0,
        retry_count=0,
        error_summary=None,
        started_at=datetime.now(timezone.utc),
        finished_at=None,
    )
    repository.session.add(trace)
    await repository.session.commit()

    span = await repository.record_runtime_span(
        trace_id=trace.id,
        node_name="retrieve_context",
        status="ok",
        input_summary="question digest",
        output_summary="retrieved 3 docs",
    )

    assert span.trace_id == trace.id
    assert span.node_name == "retrieve_context"
    assert span.status == "ok"
    assert span.input_summary == "question digest"
    assert span.output_summary == "retrieved 3 docs"
