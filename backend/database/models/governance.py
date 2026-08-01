from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKeyConstraint, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, TenantAuditMixin, money_type, utc_now


def _tenant_id_unique(table: str) -> UniqueConstraint:
    return UniqueConstraint("tenant_id", "id", name=f"uq_{table}_tenant_id_id")


class Policy(Base, TenantAuditMixin):
    __tablename__ = "policies"
    __table_args__ = (UniqueConstraint("tenant_id", "policy_code", name="uq_policies_tenant_id_policy_code"), _tenant_id_unique("policies"))

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    policy_code: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    owner_team: Mapped[str] = mapped_column(String(100), nullable=False)


class PolicyVersion(Base, TenantAuditMixin):
    __tablename__ = "policy_versions"
    __table_args__ = (
        _tenant_id_unique("policy_versions"),
        UniqueConstraint("tenant_id", "policy_id", "version_number", name="uq_policy_versions_tenant_policy_version"),
        ForeignKeyConstraint(["tenant_id", "policy_id"], ["policies.tenant_id", "policies.id"], name="fk_policy_versions_tenant_policy", ondelete="RESTRICT"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    policy_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    content_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Document(Base, TenantAuditMixin):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("tenant_id", "external_document_id", name="uq_documents_tenant_external_id"), _tenant_id_unique("documents"))

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    external_document_id: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    visibility: Mapped[str] = mapped_column(String(50), nullable=False)


class DocumentVersion(Base, TenantAuditMixin):
    __tablename__ = "document_versions"
    __table_args__ = (
        _tenant_id_unique("document_versions"),
        UniqueConstraint("tenant_id", "document_id", "version_number", name="uq_document_versions_tenant_document_version"),
        ForeignKeyConstraint(["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"], name="fk_document_versions_tenant_document", ondelete="RESTRICT"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    object_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class MemoryRecord(Base, TenantAuditMixin):
    __tablename__ = "memory_records"
    __table_args__ = (
        _tenant_id_unique("memory_records"),
        ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"], name="fk_memory_records_tenant_user", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"], name="fk_memory_records_tenant_customer", ondelete="RESTRICT"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    memory_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    ttl_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    milvus_record_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    customer_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)


class AgentDefinition(Base, TenantAuditMixin):
    __tablename__ = "agent_definitions"
    __table_args__ = (UniqueConstraint("tenant_id", "agent_code", name="uq_agent_definitions_tenant_code"), _tenant_id_unique("agent_definitions"))

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_code: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)


class AgentVersion(Base, TenantAuditMixin):
    __tablename__ = "agent_versions"
    __table_args__ = (
        _tenant_id_unique("agent_versions"),
        ForeignKeyConstraint(["tenant_id", "agent_id"], ["agent_definitions.tenant_id", "agent_definitions.id"], name="fk_agent_versions_tenant_agent", ondelete="RESTRICT"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    graph_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    config_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False)


class PromptDefinition(Base, TenantAuditMixin):
    __tablename__ = "prompt_definitions"
    __table_args__ = (UniqueConstraint("tenant_id", "prompt_code", name="uq_prompt_definitions_tenant_code"), _tenant_id_unique("prompt_definitions"))

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    prompt_code: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)


class PromptVersion(Base, TenantAuditMixin):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        _tenant_id_unique("prompt_versions"),
        ForeignKeyConstraint(["tenant_id", "prompt_id"], ["prompt_definitions.tenant_id", "prompt_definitions.id"], name="fk_prompt_versions_tenant_prompt", ondelete="RESTRICT"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    prompt_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    template_summary: Mapped[str] = mapped_column(Text, nullable=False)
    template_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)


class ModelProfile(Base, TenantAuditMixin):
    __tablename__ = "model_profiles"
    __table_args__ = (UniqueConstraint("tenant_id", "profile_code", name="uq_model_profiles_tenant_code"), _tenant_id_unique("model_profiles"))

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    profile_code: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    config_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False)


class FeatureFlag(Base, TenantAuditMixin):
    __tablename__ = "feature_flags"
    __table_args__ = (UniqueConstraint("tenant_id", "flag_key", name="uq_feature_flags_tenant_key"), _tenant_id_unique("feature_flags"))

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    flag_key: Mapped[str] = mapped_column(String(160), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)


class RuntimeTrace(Base, TenantAuditMixin):
    __tablename__ = "runtime_traces"
    __table_args__ = (UniqueConstraint("tenant_id", "trace_key", name="uq_runtime_traces_tenant_key"), _tenant_id_unique("runtime_traces"))

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trace_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    entrypoint: Mapped[str] = mapped_column(String(160), nullable=False)
    input_summary: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    model_profile_version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    prompt_version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    total_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost: Mapped[Decimal] = mapped_column(money_type(), nullable=False, default=Decimal("0.00"))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RuntimeSpan(Base, TenantAuditMixin):
    __tablename__ = "runtime_spans"
    __table_args__ = (
        _tenant_id_unique("runtime_spans"),
        ForeignKeyConstraint(["tenant_id", "trace_id"], ["runtime_traces.tenant_id", "runtime_traces.id"], name="fk_runtime_spans_tenant_trace", ondelete="RESTRICT"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    node_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    input_summary: Mapped[str] = mapped_column(Text, nullable=False)
    output_summary: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ToolExecution(Base, TenantAuditMixin):
    __tablename__ = "tool_executions"
    __table_args__ = (_tenant_id_unique("tool_executions"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trace_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    span_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    arguments_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    result_summary: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class EvaluationDataset(Base, TenantAuditMixin):
    __tablename__ = "evaluation_datasets"
    __table_args__ = (UniqueConstraint("tenant_id", "dataset_code", name="uq_evaluation_datasets_tenant_code"), _tenant_id_unique("evaluation_datasets"))

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset_code: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)


class EvaluationCase(Base, TenantAuditMixin):
    __tablename__ = "evaluation_cases"
    __table_args__ = (
        _tenant_id_unique("evaluation_cases"),
        ForeignKeyConstraint(["tenant_id", "dataset_id"], ["evaluation_datasets.tenant_id", "evaluation_datasets.id"], name="fk_evaluation_cases_tenant_dataset", ondelete="RESTRICT"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    case_key: Mapped[str] = mapped_column(String(160), nullable=False)
    input_summary: Mapped[str] = mapped_column(Text, nullable=False)
    expected_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class EvaluationRun(Base, TenantAuditMixin):
    __tablename__ = "evaluation_runs"
    __table_args__ = (_tenant_id_unique("evaluation_runs"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    agent_version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvaluationResult(Base, TenantAuditMixin):
    __tablename__ = "evaluation_results"
    __table_args__ = (_tenant_id_unique("evaluation_results"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    case_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    score: Mapped[Decimal | None] = mapped_column(money_type(), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = [name for name in globals() if name[0].isupper() and name not in {"Base", "TenantAuditMixin"}]
