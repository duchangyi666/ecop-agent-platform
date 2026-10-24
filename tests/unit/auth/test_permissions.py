from __future__ import annotations

from backend.auth.permissions import (
    ALL_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
    permissions_for_roles,
    role_has_permission,
)


def test_all_role_permissions_are_known() -> None:
    known = set(ALL_PERMISSIONS)
    for role, permissions in ROLE_PERMISSIONS.items():
        assert permissions <= known, f"{role} grants unknown permissions"


def test_finance_reviewer_can_approve_but_support_agent_cannot() -> None:
    assert role_has_permission("finance_reviewer", Permission.REFUND_APPROVE)
    assert not role_has_permission("support_agent", Permission.REFUND_APPROVE)
    assert role_has_permission("support_agent", Permission.CUSTOMER_CONSULT)


def test_permissions_for_roles_is_a_sorted_union() -> None:
    result = permissions_for_roles(["finance_reviewer", "support_agent"])

    assert result == sorted(set(result))
    assert Permission.REFUND_APPROVE in result
    assert Permission.KNOWLEDGE_SEARCH in result


def test_guest_has_minimal_permissions() -> None:
    assert ROLE_PERMISSIONS["guest"] == frozenset({Permission.KNOWLEDGE_SEARCH})
