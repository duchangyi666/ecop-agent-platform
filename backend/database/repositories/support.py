from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.base import TenantScope
from backend.database.models.billing import Customer, Refund
from backend.database.models.identity import User
from backend.database.repositories.base import TenantScopedRepository
from backend.database.models.support import ApprovalAction, ApprovalRequest, AuditLog, Ticket, TicketEvent, TicketMessage
from backend.domain.approval import ApprovalStatus, transition_approval
from backend.domain.common import DomainError
from backend.domain.ticket import TicketStatus, transition_ticket

SENSITIVE_FIELD_MARKER = "[REDACTED]"
SENSITIVE_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "card_number",
    "bank_card",
    "card_no",
    "prompt",
    "system_prompt",
    "api_key",
    "authorization",
    "private_key",
    "cookie",
}
SENSITIVE_KEY_FRAGMENTS = ("password", "secret", "token", "cardnumber", "bankcard", "systemprompt", "apikey")


def _hash_payload(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _sanitize_value(key: str, value: Any) -> Any:
    normalized_key = "".join(character for character in key.lower() if character.isalnum())
    normalized_keys = {"".join(character for character in item.lower() if character.isalnum()) for item in SENSITIVE_KEYS}
    if normalized_key in normalized_keys or any(fragment in normalized_key for fragment in SENSITIVE_KEY_FRAGMENTS):
        return SENSITIVE_FIELD_MARKER
    if isinstance(value, dict):
        return {nested_key: _sanitize_value(nested_key, nested_value) for nested_key, nested_value in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(key, item) for item in value]
    return value


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: _sanitize_value(key, value) for key, value in payload.items()}


def _extract_amount(payload: dict[str, Any]) -> Decimal | None:
    raw_amount = payload.get("amount")
    if raw_amount in (None, ""):
        return None
    try:
        return Decimal(str(raw_amount))
    except (InvalidOperation, ValueError) as exc:
        raise DomainError("approval payload amount must be Decimal-compatible") from exc


class SupportRepository(TenantScopedRepository):
    DEFAULT_APPROVAL_TTL = timedelta(hours=24)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def _get_customer_for_tenant(self, *, scope: TenantScope, customer_id: UUID) -> Customer | None:
        statement = self._tenant_visible(select(Customer), Customer, scope=scope).where(Customer.id == customer_id)
        return await self.session.scalar(statement)

    async def _get_ticket_for_tenant(self, *, scope: TenantScope, ticket_id: UUID) -> Ticket | None:
        statement = self._tenant_visible(select(Ticket), Ticket, scope=scope).where(Ticket.id == ticket_id)
        return await self.session.scalar(statement)

    async def _get_refund_for_tenant(self, *, scope: TenantScope, refund_id: UUID) -> Refund | None:
        statement = self._tenant_visible(select(Refund), Refund, scope=scope).where(Refund.id == refund_id)
        return await self.session.scalar(statement)

    async def _get_user_id_in_tenant_or_none(self, *, scope: TenantScope, user_id: UUID | None) -> UUID | None:
        if user_id is None:
            return None
        statement = self._tenant_visible(select(User.id), User, scope=scope).where(User.id == user_id).limit(1)
        return await self.session.scalar(statement)

    async def _get_required_user_id_in_tenant(self, *, scope: TenantScope, user_id: UUID | None) -> UUID | None:
        stored_user_id = await self._get_user_id_in_tenant_or_none(scope=scope, user_id=user_id)
        if user_id is not None and stored_user_id is None:
            raise DomainError("actor not found in tenant scope")
        return stored_user_id

    async def _get_approval_request_for_tenant(self, *, scope: TenantScope, approval_request_id: UUID) -> ApprovalRequest | None:
        statement = self._tenant_visible(select(ApprovalRequest), ApprovalRequest, scope=scope).where(ApprovalRequest.id == approval_request_id)
        return await self.session.scalar(statement)

    async def create_ticket(self, *, scope: TenantScope, customer_id: UUID, subject: str, priority: str) -> Ticket:
        customer = await self._get_customer_for_tenant(scope=scope, customer_id=customer_id)
        if customer is None:
            raise DomainError("customer not found in tenant scope")

        ticket = Ticket(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            customer_id=customer_id,
            subject=subject,
            description_summary=None,
            category=None,
            priority=priority,
            status=TicketStatus.OPEN,
            current_assignee_id=None,
            resolved_at=None,
        )
        self.session.add(ticket)
        await self.session.flush()
        return ticket

    async def append_ticket_message(
        self,
        *,
        scope: TenantScope,
        ticket_id: UUID,
        author_id: UUID | None,
        body: str,
        visibility: str,
    ) -> TicketMessage:
        ticket = await self._get_ticket_for_tenant(scope=scope, ticket_id=ticket_id)
        if ticket is None:
            raise DomainError("ticket not found in tenant scope")
        stored_author_id = await self._get_user_id_in_tenant_or_none(scope=scope, user_id=author_id)

        message = TicketMessage(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            ticket_id=ticket_id,
            author_id=stored_author_id,
            body=body,
            visibility=visibility,
        )
        self.session.add(message)
        self.session.add(
            TicketEvent(
                id=uuid4(),
                tenant_id=scope.tenant_id,
                ticket_id=ticket_id,
                actor_id=stored_author_id,
                event_type="message_appended",
                from_status=None,
                to_status=ticket.status,
                payload_summary={"visibility": visibility},
            )
        )
        await self.session.flush()
        return message

    async def create_approval_request(
        self,
        *,
        scope: TenantScope,
        ticket_id: UUID,
        action: str,
        payload: dict[str, Any],
        approval_role: str,
    ) -> ApprovalRequest:
        ticket = await self._get_ticket_for_tenant(scope=scope, ticket_id=ticket_id)
        if ticket is None:
            raise DomainError("ticket not found in tenant scope")
        stored_actor_id = await self._get_user_id_in_tenant_or_none(scope=scope, user_id=scope.actor_id)

        sanitized_payload = _sanitize_payload(payload)
        amount = _extract_amount(payload)
        previous_status = ticket.status
        approval = ApprovalRequest(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            ticket_id=ticket_id,
            requested_by_user_id=stored_actor_id,
            action=action,
            payload_summary=sanitized_payload,
            payload_hash=_hash_payload(payload),
            amount=amount,
            risk_level="high" if amount is not None and amount >= Decimal("100.00") else "standard",
            approval_role=approval_role,
            status=ApprovalStatus.PENDING,
            expires_at=ticket.updated_at + self.DEFAULT_APPROVAL_TTL,
            checkpoint_reference=str(payload.get("checkpoint_reference")) if payload.get("checkpoint_reference") else None,
        )
        approval.actions = []
        ticket.status = transition_ticket(ticket.status, TicketStatus.PENDING_APPROVAL)
        self.session.add(approval)
        self.session.add(
            TicketEvent(
                id=uuid4(),
                tenant_id=scope.tenant_id,
                ticket_id=ticket_id,
                actor_id=stored_actor_id,
                event_type="approval_requested",
                from_status=previous_status,
                to_status=TicketStatus.PENDING_APPROVAL,
                payload_summary={"approval_role": approval_role, "action": action},
            )
        )
        await self.session.flush()
        return approval

    async def create_refund_approval_request(
        self,
        *,
        scope: TenantScope,
        refund_id: UUID,
        action: str,
        payload: dict[str, Any],
        approval_role: str,
        checkpoint_reference: str | None = None,
    ) -> ApprovalRequest:
        refund = await self._get_refund_for_tenant(scope=scope, refund_id=refund_id)
        if refund is None:
            raise DomainError("refund not found in tenant scope")

        stored_actor_id = await self._get_user_id_in_tenant_or_none(scope=scope, user_id=scope.actor_id)
        sanitized_payload = _sanitize_payload(payload)
        approval = ApprovalRequest(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            ticket_id=None,
            refund_id=refund.id,
            requested_by_user_id=stored_actor_id,
            action=action,
            payload_summary=sanitized_payload,
            payload_hash=_hash_payload(payload),
            amount=_extract_amount(payload) or refund.amount,
            risk_level="high",
            approval_role=approval_role,
            status=ApprovalStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + self.DEFAULT_APPROVAL_TTL,
            checkpoint_reference=checkpoint_reference,
        )
        self.session.add(approval)
        await self.session.flush()
        return approval

    async def get_approval_request_for_tenant(
        self,
        *,
        scope: TenantScope,
        approval_request_id: UUID,
    ) -> ApprovalRequest | None:
        return await self._get_approval_request_for_tenant(
            scope=scope,
            approval_request_id=approval_request_id,
        )

    async def append_approval_action(
        self,
        *,
        scope: TenantScope,
        approval_request_id: UUID,
        action: str,
        reason: str,
        changes: dict[str, Any],
    ) -> ApprovalAction:
        approval_request = await self._get_approval_request_for_tenant(scope=scope, approval_request_id=approval_request_id)
        if approval_request is None:
            raise DomainError("approval request not found in tenant scope")
        stored_actor_id = await self._get_user_id_in_tenant_or_none(scope=scope, user_id=scope.actor_id)

        sanitized_changes = _sanitize_payload(changes)
        approval_action = ApprovalAction(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            approval_request_id=approval_request_id,
            actor_id=stored_actor_id,
            action=action,
            reason=reason,
            changes_summary=sanitized_changes,
        )
        try:
            target_status = ApprovalStatus(action)
        except ValueError as exc:
            raise DomainError(f"unsupported approval action: {action}") from exc
        approval_request.status = transition_approval(approval_request.status, target_status)
        approval_request.actions.append(approval_action)
        self.session.add(approval_action)
        await self.session.flush()
        return approval_action

    async def append_audit_log(
        self,
        *,
        scope: TenantScope | None,
        actor_id: UUID | None,
        action: str,
        resource_type: str,
        resource_id: UUID | None,
        metadata: dict[str, Any],
    ) -> AuditLog:
        if scope is None and resource_type != "platform":
            raise DomainError("business audit events require tenant scope")

        stored_actor_id = actor_id
        if scope is not None:
            stored_actor_id = await self._get_required_user_id_in_tenant(scope=scope, user_id=actor_id)

        sanitized_metadata = _sanitize_payload(metadata)
        log = AuditLog(
            id=uuid4(),
            tenant_id=scope.tenant_id if scope is not None else None,
            actor_id=stored_actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_summary=sanitized_metadata,
            metadata_hash=_hash_payload(metadata),
        )
        self.session.add(log)
        await self.session.flush()
        return log


__all__ = ["SupportRepository"]
