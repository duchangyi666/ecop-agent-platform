"""Canonical RBAC catalog.

The database remains the source of truth for a user's effective permissions;
this module is the reviewed matrix used by provisioning, tests and the
`/auth/me` contract. Adding a permission here requires updating routes and the
role matrix in the same change.
"""

from __future__ import annotations

from typing import Final


class Permission(str):
    CUSTOMER_CONSULT = "customer.consult"
    CONVERSATION_CREATE = "conversation.create"
    CONVERSATION_READ = "conversation.read"
    CONVERSATION_READ_ALL = "conversation.read.all"
    CONVERSATION_WRITE_ALL = "conversation.write.all"
    CONVERSATION_WRITE = "conversation.write"
    TICKET_CREATE = "ticket.create"
    TICKET_READ = "ticket.read"
    TICKET_UPDATE = "ticket.update"
    REFUND_REQUEST = "refund.request"
    REFUND_APPROVE = "refund.approve"
    APPROVAL_READ = "approval.read"
    KNOWLEDGE_SEARCH = "knowledge.search"
    KNOWLEDGE_INGEST = "knowledge.ingest"
    KNOWLEDGE_DELETE = "knowledge.delete"
    EVALUATION_READ = "evaluation.read"
    EVALUATION_RUN = "evaluation.run"
    RUNTIME_READ = "runtime.read"


ALL_PERMISSIONS: Final[tuple[str, ...]] = (
    Permission.CUSTOMER_CONSULT,
    Permission.CONVERSATION_CREATE,
    Permission.CONVERSATION_READ,
    Permission.CONVERSATION_WRITE,
    Permission.CONVERSATION_READ_ALL,
    Permission.CONVERSATION_WRITE_ALL,
    Permission.TICKET_CREATE,
    Permission.TICKET_READ,
    Permission.TICKET_UPDATE,
    Permission.REFUND_REQUEST,
    Permission.REFUND_APPROVE,
    Permission.APPROVAL_READ,
    Permission.KNOWLEDGE_SEARCH,
    Permission.KNOWLEDGE_INGEST,
    Permission.KNOWLEDGE_DELETE,
    Permission.EVALUATION_READ,
    Permission.EVALUATION_RUN,
    Permission.RUNTIME_READ,
)

ROLE_PERMISSIONS: Final[dict[str, frozenset[str]]] = {
    "platform_admin": frozenset(ALL_PERMISSIONS),
    "support_manager": frozenset(
        {
            Permission.CUSTOMER_CONSULT,
            Permission.CONVERSATION_CREATE,
            Permission.CONVERSATION_READ,
            Permission.CONVERSATION_WRITE,
            Permission.CONVERSATION_READ_ALL,
            Permission.CONVERSATION_WRITE_ALL,
            Permission.TICKET_CREATE,
            Permission.TICKET_READ,
            Permission.TICKET_UPDATE,
            Permission.APPROVAL_READ,
            Permission.REFUND_REQUEST,
            Permission.KNOWLEDGE_SEARCH,
            Permission.KNOWLEDGE_INGEST,
            Permission.EVALUATION_READ,
            Permission.RUNTIME_READ,
        }
    ),
    "support_agent": frozenset(
        {
            Permission.CUSTOMER_CONSULT,
            Permission.CONVERSATION_CREATE,
            Permission.CONVERSATION_READ,
            Permission.CONVERSATION_WRITE,
            Permission.CONVERSATION_READ_ALL,
            Permission.CONVERSATION_WRITE_ALL,
            Permission.TICKET_CREATE,
            Permission.TICKET_READ,
            Permission.TICKET_UPDATE,
            Permission.APPROVAL_READ,
            Permission.KNOWLEDGE_SEARCH,
        }
    ),
    "finance_reviewer": frozenset(
        {
            Permission.CUSTOMER_CONSULT,
            Permission.CONVERSATION_READ,
            Permission.CONVERSATION_READ_ALL,
            Permission.REFUND_REQUEST,
            Permission.REFUND_APPROVE,
            Permission.APPROVAL_READ,
            Permission.RUNTIME_READ,
        }
    ),
    "customer": frozenset(
        {
            Permission.CUSTOMER_CONSULT,
            Permission.CONVERSATION_CREATE,
            Permission.CONVERSATION_READ,
            Permission.CONVERSATION_WRITE,
            Permission.TICKET_CREATE,
            Permission.TICKET_READ,
            Permission.KNOWLEDGE_SEARCH,
        }
    ),
    "guest": frozenset({Permission.KNOWLEDGE_SEARCH}),
}


def permissions_for_roles(role_codes: list[str] | set[str] | tuple[str, ...]) -> list[str]:
    granted: set[str] = set()
    for code in role_codes:
        granted.update(ROLE_PERMISSIONS.get(code, frozenset()))
    return sorted(granted)


def role_has_permission(role_code: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role_code, frozenset())


__all__ = [
    "ALL_PERMISSIONS",
    "Permission",
    "ROLE_PERMISSIONS",
    "permissions_for_roles",
    "role_has_permission",
]
