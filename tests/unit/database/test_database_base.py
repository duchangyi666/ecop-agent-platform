from decimal import Decimal

from backend.database.base import Base, money_type


def test_base_uses_named_constraints() -> None:
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"
    assert Base.metadata.naming_convention["uq"] == "uq_%(table_name)s_%(column_0_name)s"


def test_money_columns_are_not_float() -> None:
    assert money_type().python_type is Decimal
