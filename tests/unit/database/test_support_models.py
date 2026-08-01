from decimal import Decimal

from backend.database.base import Base
from backend.domain.approval import ApprovalStatus
from backend.domain.ticket import TicketStatus
from tests.unit.database.helpers import find_constraint


def test_ticket_status_is_enum_backed() -> None:
    from backend.database.models.support import Ticket

    assert Ticket.__table__.c.status.type.enum_class is TicketStatus


def test_approval_expiration_is_stored_in_utc() -> None:
    from backend.database.models.support import ApprovalRequest

    assert ApprovalRequest.__table__.c.expires_at.type.timezone is True


def test_approval_amount_uses_decimal_precision() -> None:
    from backend.database.models.support import ApprovalRequest

    amount_column = ApprovalRequest.__table__.c.amount
    assert amount_column.type.asdecimal is True
    assert amount_column.type.precision == 18
    assert amount_column.type.scale == 2


def test_approval_status_is_enum_backed() -> None:
    from backend.database.models.support import ApprovalRequest

    assert ApprovalRequest.__table__.c.status.type.enum_class is ApprovalStatus


def test_ticket_assignment_uses_tenant_scoped_foreign_keys(metadata) -> None:
    constraint = find_constraint(
        "ticket_assignments",
        "fk_ticket_assignments_tenant_user",
        metadata,
    )
    assert constraint is not None


def test_audit_logs_allow_platform_level_events() -> None:
    from backend.database.models.support import AuditLog

    assert AuditLog.__table__.c.tenant_id.nullable is True


def test_support_models_are_registered_on_shared_metadata() -> None:
    assert Base.metadata.tables["tickets"] is not None
    assert Base.metadata.tables["approval_requests"] is not None
    assert Base.metadata.tables["audit_logs"] is not None

