from __future__ import annotations

from uuid import uuid4

from backend.agent.checkpoint import DatabaseCheckpointStore
from backend.database.repositories.governance import _sanitize


def test_database_checkpoint_store_is_constructible() -> None:
    assert DatabaseCheckpointStore is not None


def test_checkpoint_summary_sanitizes_uuid_values_for_json_storage() -> None:
    value = uuid4()

    assert _sanitize({"refund_id": value}) == {"refund_id": str(value)}
