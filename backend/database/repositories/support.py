from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database.base import TenantScope
from backend.database.models.billing import Customer, CustomerContact, Refund
from backend.database.models.identity import User
from backend.database.repositories.base import TenantScopedRepository
from backend.database.models.support import (
    ApprovalAction,
    ApprovalRequest,
    AuditLog,
    Conversation,
    ConversationMessage,
    Ticket,
    TicketEvent,
    TicketMessage,
)
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

    async def _get_approval_request_for_tenant(
        self, *, scope: TenantScope, approval_request_id: UUID, for_update: bool = False,
    ) -> ApprovalRequest | None:
        statement = (
            self._tenant_visible(select(ApprovalRequest), ApprovalRequest, scope=scope)
            .options(selectinload(ApprovalRequest.actions))
            .where(ApprovalRequest.id == approval_request_id)
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return await self.session.scalar(statement)

    async def create_ticket(
        self,
        *,
        scope: TenantScope,
        customer_id: UUID,
        subject: str,
        priority: str,
        description_summary: str | None = None,
        category: str | None = None,
        initial_message: str | None = None,
    ) -> Ticket:
        customer = await self._get_customer_for_tenant(scope=scope, customer_id=customer_id)
        if customer is None:
            raise DomainError("customer not found in tenant scope")

        ticket = Ticket(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            customer_id=customer_id,
            subject=subject,
            description_summary=description_summary,
            category=category,
            priority=priority,
            status=TicketStatus.OPEN,
            current_assignee_id=None,
            resolved_at=None,
        )
        self.session.add(ticket)
        self.session.add(
            TicketEvent(
                id=uuid4(),
                tenant_id=scope.tenant_id,
                ticket_id=ticket.id,
                actor_id=None,
                event_type="ticket_created",
                from_status=None,
                to_status=TicketStatus.OPEN,
                payload_summary={"priority": priority},
            )
        )
        if initial_message:
            self.session.add(
                TicketMessage(
                    id=uuid4(),
                    tenant_id=scope.tenant_id,
                    ticket_id=ticket.id,
                    author_id=None,
                    body=initial_message,
                    visibility="internal",
                )
            )
        await self.session.flush()
        return ticket

    async def list_tickets_for_customer(
        self,
        *,
        scope: TenantScope,
        customer_id: UUID,
        limit: int = 5,
    ) -> list[Ticket]:
        statement = self._tenant_visible(select(Ticket), Ticket, scope=scope).where(
            Ticket.customer_id == customer_id,
            Ticket.deleted_at.is_(None),
        )
        result = await self.session.scalars(statement.order_by(Ticket.created_at.desc()).limit(limit))
        return list(result.all())

    async def update_ticket_status(
        self,
        *,
        scope: TenantScope,
        ticket_id: UUID,
        target_status: TicketStatus,
        actor_id: UUID | None,
        reason: str,
        changes: dict[str, Any] | None = None,
    ) -> Ticket:
        ticket = await self._get_ticket_for_tenant(scope=scope, ticket_id=ticket_id)
        if ticket is None:
            raise DomainError("ticket not found in tenant scope")

        previous_status = ticket.status
        ticket.status = transition_ticket(ticket.status, target_status)
        stored_actor_id = await self._get_user_id_in_tenant_or_none(scope=scope, user_id=actor_id)
        sanitized_changes = _sanitize_payload(changes or {})
        self.session.add(
            TicketEvent(
                id=uuid4(),
                tenant_id=scope.tenant_id,
                ticket_id=ticket.id,
                actor_id=stored_actor_id,
                event_type="status_changed",
                from_status=previous_status,
                to_status=ticket.status,
                payload_summary={"reason": reason[:500], **sanitized_changes},
            )
        )
        self.session.add(
            TicketMessage(
                id=uuid4(),
                tenant_id=scope.tenant_id,
                ticket_id=ticket.id,
                author_id=stored_actor_id,
                body=reason,
                visibility="internal",
            )
        )
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
        for_update: bool = False,
    ) -> ApprovalRequest | None:
        return await self._get_approval_request_for_tenant(
            scope=scope,
            approval_request_id=approval_request_id,
            for_update=for_update,
        )

    async def get_refund_approval(self, *, scope: TenantScope, refund_id: UUID) -> ApprovalRequest | None:
        statement = self._tenant_visible(select(ApprovalRequest), ApprovalRequest, scope=scope).where(
            ApprovalRequest.refund_id == refund_id,
            ApprovalRequest.action == "approve_refund",
        ).order_by(ApprovalRequest.created_at, ApprovalRequest.id).limit(1)
        return await self.session.scalar(statement)

    async def append_approval_action(
        self,
        *,
        scope: TenantScope,
        approval_request_id: UUID,
        action: str,
        reason: str,
        changes: dict[str, Any],
    ) -> ApprovalAction:
        approval_request = await self._get_approval_request_for_tenant(
            scope=scope, approval_request_id=approval_request_id, for_update=True,
        )
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

    async def create_conversation(
        self,
        *,
        scope: TenantScope,
        customer_id: UUID | None,
        user_id: UUID | None,
        channel: str,
        subject: str,
    ) -> Conversation:
        if customer_id is not None:
            customer = await self._get_customer_for_tenant(scope=scope, customer_id=customer_id)
            if customer is None:
                raise DomainError("customer not found in tenant scope")
        stored_user_id = await self._get_user_id_in_tenant_or_none(scope=scope, user_id=user_id)
        conversation = Conversation(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            customer_id=customer_id,
            user_id=stored_user_id,
            channel=channel,
            subject=subject,
            status="open",
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get_conversation_by_thread(
        self,
        *,
        scope: TenantScope,
        thread_id: str,
    ) -> Conversation | None:
        statement = self._tenant_visible(select(Conversation), Conversation, scope=scope).where(
            Conversation.thread_id == thread_id,
            Conversation.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def list_conversations(
        self,
        *,
        scope: TenantScope,
        limit: int = 50,
        status: str | None = None,
        owner_id: UUID | None = None,
    ) -> list[Conversation]:
        statement = (
            self._tenant_visible(
                select(Conversation),
                Conversation,
                scope=scope,
            )
            .options(selectinload(Conversation.messages))
        )
        if owner_id is not None:
            statement = statement.where(Conversation.user_id == owner_id)
        if status:
            statement = statement.where(Conversation.status == status)
        statement = statement.order_by(Conversation.started_at.desc()).limit(limit)
        return list(await self.session.scalars(statement))

    async def get_conversation(
        self,
        *,
        scope: TenantScope,
        conversation_id: UUID,
        owner_id: UUID | None = None,
    ) -> Conversation | None:
        statement = (
            self._tenant_visible(
                select(Conversation),
                Conversation,
                scope=scope,
            )
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )
        if owner_id is not None:
            statement = statement.where(Conversation.user_id == owner_id)
        return await self.session.scalar(statement)

    async def append_conversation_message(
        self,
        *,
        scope: TenantScope,
        conversation_id: UUID,
        author_id: UUID | None,
        author_type: str,
        role: str,
        body: str,
        visibility: str,
    ) -> ConversationMessage:
        conversation = await self.get_conversation(scope=scope, conversation_id=conversation_id)
        if conversation is None:
            raise DomainError("conversation not found in tenant scope")
        stored_author_id = await self._get_user_id_in_tenant_or_none(scope=scope, user_id=author_id)
        message = ConversationMessage(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            conversation_id=conversation_id,
            author_id=stored_author_id,
            author_type=author_type,
            role=role,
            body=body,
            visibility=visibility,
        )
        self.session.add(message)
        conversation.messages.append(message)
        await self.session.flush()
        return message

    async def update_conversation_status(
        self,
        *,
        scope: TenantScope,
        conversation_id: UUID,
        target_status: str,
        actor_id: UUID | None,
        reason: str,
    ) -> Conversation:
        conversation = await self.get_conversation(scope=scope, conversation_id=conversation_id)
        if conversation is None:
            raise DomainError("conversation not found in tenant scope")
        allowed = {
            "open",
            "in_progress",
            "pending_customer",
            "escalated",
            "resolved",
            "closed",
            "cancelled",
        }
        if target_status not in allowed:
            raise DomainError(f"unsupported conversation status: {target_status}")
        conversation.status = target_status
        if target_status in {"resolved", "closed"}:
            conversation.resolved_at = datetime.now(timezone.utc)
        stored_author_id = await self._get_user_id_in_tenant_or_none(scope=scope, user_id=actor_id)
        self.session.add(
            ConversationMessage(
                id=uuid4(),
                tenant_id=scope.tenant_id,
                conversation_id=conversation_id,
                author_id=stored_author_id,
                author_type="system" if actor_id is None else "user",
                role="system",
                body=reason[:500],
                visibility="internal",
            )
        )
        await self.session.flush()
        return conversation

    async def list_tickets(
        self,
        *,
        scope: TenantScope,
        limit: int = 50,
        status: str | None = None,
        owner_id: UUID | None = None,
    ) -> list[Ticket]:
        statement = self._tenant_visible(
            select(Ticket),
            Ticket,
            scope=scope,
        )
        if owner_id is not None:
            statement = statement.where(Ticket.customer_id.in_(select(CustomerContact.customer_id).where(
                CustomerContact.tenant_id == scope.tenant_id,
                CustomerContact.user_id == owner_id,
                CustomerContact.deleted_at.is_(None),
            )))
        if status:
            statement = statement.where(Ticket.status == status)
        statement = statement.order_by(Ticket.updated_at.desc()).limit(limit)
        return list(await self.session.scalars(statement))

    async def get_ticket_detail(
        self,
        *,
        scope: TenantScope,
        ticket_id: UUID,
        owner_id: UUID | None = None,
    ) -> Ticket | None:
        statement = (
            self._tenant_visible(
                select(Ticket),
                Ticket,
                scope=scope,
            )
            .options(
                selectinload(Ticket.messages),
                selectinload(Ticket.events),
                selectinload(Ticket.approval_requests),
            )
            .where(Ticket.id == ticket_id)
        )
        if owner_id is not None:
            statement = statement.where(Ticket.customer_id.in_(select(CustomerContact.customer_id).where(
                CustomerContact.tenant_id == scope.tenant_id,
                CustomerContact.user_id == owner_id,
                CustomerContact.deleted_at.is_(None),
            )))
        return await self.session.scalar(statement)

    async def update_ticket_metadata(
        self,
        *,
        scope: TenantScope,
        ticket_id: UUID,
        subject: str | None,
        description_summary: str | None,
        priority: str | None,
        note: str | None,
        actor_id: UUID | None,
    ) -> Ticket:
        ticket = await self._get_ticket_for_tenant(scope=scope, ticket_id=ticket_id)
        if ticket is None:
            raise DomainError("ticket not found in tenant scope")
        changes: dict[str, str] = {}
        if subject is not None:
            ticket.subject = subject
            changes["subject"] = subject
        if description_summary is not None:
            ticket.description_summary = description_summary
            changes["description_summary"] = description_summary
        if priority is not None:
            ticket.priority = priority
            changes["priority"] = priority
        if note:
            stored_actor_id = await self._get_user_id_in_tenant_or_none(scope=scope, user_id=actor_id)
            self.session.add(
                TicketMessage(
                    id=uuid4(),
                    tenant_id=scope.tenant_id,
                    ticket_id=ticket.id,
                    author_id=stored_actor_id,
                    body=note,
                    visibility="internal",
                )
            )
            changes["note_added"] = "true"
        self.session.add(
            TicketEvent(
                id=uuid4(),
                tenant_id=scope.tenant_id,
                ticket_id=ticket.id,
                actor_id=await self._get_user_id_in_tenant_or_none(scope=scope, user_id=actor_id),
                event_type="ticket_updated",
                from_status=ticket.status,
                to_status=ticket.status,
                payload_summary=_sanitize_payload(changes),
            )
        )
        await self.session.flush()
        return ticket

    async def list_approval_requests(
        self,
        *,
        scope: TenantScope,
        limit: int = 50,
        status: str | None = None,
        as_of: datetime | None = None,
    ) -> list[ApprovalRequest]:
        statement = (
            self._tenant_visible(
                select(ApprovalRequest),
                ApprovalRequest,
                scope=scope,
            )
            .options(selectinload(ApprovalRequest.actions))
        )
        if status == ApprovalStatus.PENDING.value:
            statement = statement.where(
                ApprovalRequest.status == ApprovalStatus.PENDING,
                ApprovalRequest.expires_at > (as_of or datetime.now(timezone.utc)),
            )
        elif status == ApprovalStatus.EXPIRED.value:
            statement = statement.where(or_(
                ApprovalRequest.status == ApprovalStatus.EXPIRED,
                and_(ApprovalRequest.status == ApprovalStatus.PENDING,
                     ApprovalRequest.expires_at <= (as_of or datetime.now(timezone.utc))),
            ))
        elif status:
            statement = statement.where(ApprovalRequest.status == status)
        statement = statement.order_by(ApprovalRequest.expires_at).limit(limit)
        return list(await self.session.scalars(statement))


__all__ = ["SupportRepository"]
