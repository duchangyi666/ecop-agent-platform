from backend.database.base import Base
from tests.unit.database.helpers import find_constraint


def test_tenant_slug_is_globally_unique(metadata) -> None:
    constraint = find_constraint("tenants", "uq_tenants_slug", metadata)
    assert constraint is not None


def test_user_email_is_unique_inside_tenant(metadata) -> None:
    constraint = find_constraint("users", "uq_users_tenant_id_email", metadata)
    assert constraint is not None


def test_role_code_is_unique_inside_tenant(metadata) -> None:
    constraint = find_constraint("roles", "uq_roles_tenant_id_code", metadata)
    assert constraint is not None


def test_user_role_assignment_is_unique_inside_tenant(metadata) -> None:
    constraint = find_constraint("user_roles", "uq_user_roles_tenant_id_user_id_role_id", metadata)
    assert constraint is not None
