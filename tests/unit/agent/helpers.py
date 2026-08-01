from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from backend.agent.state import AgentState, create_agent_state
from backend.database.base import TenantScope


@pytest.fixture
def scope() -> TenantScope:
    return TenantScope(tenant_id=uuid4())


@pytest.fixture
def request_id() -> UUID:
    return uuid4()


def state_for_message(*, scope: TenantScope, request_id: UUID, message: str) -> AgentState:
    return create_agent_state(scope=scope, request_id=request_id, message=message)
