"""Reproduce the suspected NameError in CustomerConsultationService.run().

Uses mocks for the graph, database session and memory service so the
persistence path is exercised without needing PostgreSQL.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.agent.consultation_workflow import (
    CustomerConsultationService,
    CustomerConsultationWorkflowRequest,
)
from backend.agent.state import create_agent_state
from backend.database.base import TenantScope
from backend.llm.contracts import ResponseDraft
from backend.llm.fake import FakeModelGateway


class FakeUoW:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        self.governance = MagicMock()
        self.support = MagicMock()
        self.identity = MagicMock()
        self.governance.create_runtime_trace = AsyncMock(
            return_value=SimpleNamespace(id=uuid4())
        )
        self.governance.complete_runtime_trace = AsyncMock()
        self.governance.record_runtime_span = AsyncMock()
        self.support.append_audit_log = AsyncMock(
            return_value=SimpleNamespace(id=uuid4())
        )
        self.support.get_conversation_by_thread = AsyncMock(return_value=None)
        self.support.create_conversation = AsyncMock(
            return_value=SimpleNamespace(id=uuid4())
        )
        self.support.append_conversation_message = AsyncMock()
        self.identity.get_customer_for_user = AsyncMock(return_value=None)
        return self

    async def __aexit__(self, *args):
        pass


async def main() -> None:
    scope = TenantScope(tenant_id=uuid4(), actor_id=uuid4(), actor_type="user")
    state = create_agent_state(scope=scope, request_id=uuid4(), message="你好，我要退款")
    request = CustomerConsultationWorkflowRequest(thread_id="t-repro", state=state)
    gateway = FakeModelGateway(
        ResponseDraft(answer="好的", next_action="finish", confidence=0.9)
    )
    fake_state = {
        "status": "completed",
        "next_action": "finish",
        "final_response": "好的",
        "response_review": None,
        "knowledge_evidence": [],
    }
    with (
        patch("backend.agent.consultation_workflow.build_main_graph") as mb,
        patch("backend.agent.consultation_workflow.UnitOfWork", FakeUoW),
        patch("backend.agent.consultation_workflow.MemoryService") as mms,
    ):
        graph = mb.return_value
        graph.compile.return_value.ainvoke = AsyncMock(return_value=fake_state)
        mms.return_value.capture_in_uow = AsyncMock(return_value=[])
        service = CustomerConsultationService("fake_factory", model_gateway=gateway)
        try:
            result = await service.run(request)
            print(f"NO ERROR - unexpected, result status={result.status}")
        except NameError as exc:
            print(f"REPRODUCED NameError: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"OTHER ERROR: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
