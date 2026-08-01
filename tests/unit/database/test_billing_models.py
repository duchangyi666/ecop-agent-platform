from decimal import Decimal

from backend.database.base import Base
from backend.database.models.billing import Payment, Refund
from tests.unit.database.helpers import find_constraint


def test_payment_amount_uses_decimal() -> None:
    assert Payment.__table__.c.amount.type.asdecimal is True
    assert Payment.__table__.c.amount.type.precision == 18
    assert Payment.__table__.c.amount.type.scale == 2


def test_refund_has_tenant_scoped_idempotency_constraint(metadata) -> None:
    constraint = find_constraint(
        "refunds",
        "uq_refunds_tenant_id_idempotency_key",
        metadata,
    )
    assert constraint is not None


def test_payment_external_id_is_unique_inside_tenant(metadata) -> None:
    constraint = find_constraint(
        "payments",
        "uq_payments_tenant_id_external_payment_id",
        metadata,
    )
    assert constraint is not None


def test_refund_status_uses_unknown_execution_value() -> None:
    status_column = Refund.__table__.c.status
    assert status_column.nullable is False
    assert "unknown_execution_state" in status_column.type.enums


def test_billing_models_are_registered_on_shared_metadata() -> None:
    assert Base.metadata.tables["customers"] is not None
    assert Base.metadata.tables["payments"] is not None
    assert Base.metadata.tables["refunds"] is not None
