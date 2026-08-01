"""Model registry for Alembic autogeneration."""

from backend.database.base import Base
from backend.database.models.billing import Customer, CustomerContact, Invoice, Payment, Refund, Subscription
from backend.database.models.identity import Permission, Role, Tenant, User, UserRole
from backend.database.models.support import ApprovalAction, ApprovalRequest, AuditLog, Ticket, TicketAssignment, TicketEvent, TicketMessage

__all__ = [
    "ApprovalAction",
    "ApprovalRequest",
    "AuditLog",
    "Base",
    "Customer",
    "CustomerContact",
    "Invoice",
    "Payment",
    "Permission",
    "Refund",
    "Role",
    "Subscription",
    "Tenant",
    "Ticket",
    "TicketAssignment",
    "TicketEvent",
    "TicketMessage",
    "User",
    "UserRole",
]
