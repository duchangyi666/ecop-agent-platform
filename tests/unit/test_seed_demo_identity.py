from __future__ import annotations


def test_seed_demo_identity_exposes_explicit_permission_codes() -> None:
    from scripts.seed_demo_identity import SUPPORTED_PERMISSIONS

    assert SUPPORTED_PERMISSIONS == {
        "approval.read",
        "conversation.create",
        "conversation.read",
        "conversation.write",
        "refund.request",
        "refund.approve",
        "customer.consult",
        "ticket.create",
        "ticket.read",
        "ticket.update",
        "knowledge.search",
        "knowledge.ingest",
        "knowledge.delete",
        "evaluation.read",
        "evaluation.run",
        "runtime.read",
    }
