from __future__ import annotations

from backend.database.base import Base
from backend.database.models.governance import WorkflowCheckpoint
from backend.database.models.support import ApprovalRequest


def test_approval_request_can_target_refund_without_ticket() -> None:
    columns = {column.name for column in ApprovalRequest.__table__.columns}

    assert "refund_id" in columns
    assert ApprovalRequest.__table__.c.ticket_id.nullable is True
    assert ApprovalRequest.__table__.c.refund_id.nullable is True


def test_workflow_checkpoint_is_tenant_scoped_and_thread_unique() -> None:
    table = WorkflowCheckpoint.__table__

    assert "tenant_id" in table.c
    assert "state_summary" in table.c
    assert any(
        constraint.name == "uq_workflow_checkpoints_tenant_thread"
        for constraint in table.constraints
    )


def test_workflow_checkpoint_is_registered_on_shared_metadata() -> None:
    assert Base.metadata.tables["workflow_checkpoints"] is WorkflowCheckpoint.__table__
