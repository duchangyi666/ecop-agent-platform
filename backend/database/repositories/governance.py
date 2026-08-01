from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.base import TenantScope
from backend.database.models.governance import MemoryRecord, Policy, PolicyVersion, RuntimeSpan, RuntimeTrace
from backend.domain.common import DomainError

SENSITIVE_MARKER = "[REDACTED]"
_SENSITIVE_FRAGMENTS = ("password", "secret", "token", "cardnumber", "bankcard", "systemprompt", "apikey", "prompt")


def _normalize_key(key: str) -> str:
    return "".join(character for character in key.lower() if character.isalnum())


def _sanitize(value: Any, key: str = "") -> Any:
    normalized = _normalize_key(key)
    if any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS):
        return SENSITIVE_MARKER
    if isinstance(value, dict):
        return {str(item_key): _sanitize(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_sanitize(item, key) for item in value]
    return value


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class GovernanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_published_policy(self, *, scope: TenantScope, policy_code: str, at: datetime) -> PolicyVersion | None:
        if at.tzinfo is None or at.utcoffset() is None:
            raise DomainError("policy lookup time must be timezone-aware")
        statement = (
            select(PolicyVersion)
            .join(Policy, and_(Policy.id == PolicyVersion.policy_id, Policy.tenant_id == PolicyVersion.tenant_id))
            .where(
                PolicyVersion.tenant_id == scope.tenant_id,
                PolicyVersion.deleted_at.is_(None),
                Policy.tenant_id == scope.tenant_id,
                Policy.deleted_at.is_(None),
                Policy.policy_code == policy_code,
                Policy.status == "active",
                PolicyVersion.status == "published",
                PolicyVersion.effective_from <= at,
                or_(PolicyVersion.effective_to.is_(None), PolicyVersion.effective_to > at),
            )
            .order_by(PolicyVersion.version_number.desc())
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def add_memory_candidate(
        self,
        *,
        scope: TenantScope,
        user_id: UUID | None,
        customer_id: UUID | None,
        payload: dict[str, Any],
    ) -> MemoryRecord:
        now = datetime.now(timezone.utc)
        record = MemoryRecord(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            memory_type=str(payload.get("memory_type", "conversation")),
            payload_summary=_sanitize(payload),
            payload_hash=_hash_payload(payload),
            source=str(payload.get("source", "conversation")),
            confidence=float(payload.get("confidence", 0.0)),
            ttl_expires_at=now + timedelta(days=int(payload.get("ttl_days", 30))),
            last_verified_at=None,
            milvus_record_id=None,
            user_id=user_id,
            customer_id=customer_id,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def record_runtime_span(
        self,
        *,
        trace_id: UUID,
        node_name: str,
        status: str,
        input_summary: str,
        output_summary: str,
    ) -> RuntimeSpan:
        trace = await self.session.get(RuntimeTrace, trace_id)
        if trace is None or trace.deleted_at is not None:
            raise DomainError("runtime trace not found")
        span = RuntimeSpan(
            id=uuid4(),
            tenant_id=trace.tenant_id,
            trace_id=trace.id,
            node_name=node_name,
            status=status,
            input_summary=input_summary,
            output_summary=output_summary,
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            duration_ms=None,
        )
        self.session.add(span)
        await self.session.flush()
        return span


__all__ = ["GovernanceRepository"]
