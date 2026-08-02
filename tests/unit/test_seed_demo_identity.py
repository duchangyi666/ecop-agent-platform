from __future__ import annotations


def test_seed_demo_identity_exposes_explicit_permission_codes() -> None:
    from scripts.seed_demo_identity import SUPPORTED_PERMISSIONS

    assert SUPPORTED_PERMISSIONS == {"refund.request", "refund.approve", "customer.consult"}
