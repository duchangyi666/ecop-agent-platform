from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.agent.actions import ActionDecision, ActionResult, ConversationActionExecutor
from backend.auth.permissions import Permission
from backend.database.base import TenantScope
from backend.database.models.identity import User


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "permission", "method"),
    [
        ("request_refund", Permission.REFUND_REQUEST, "_request_refund"),
        ("create_ticket", Permission.TICKET_CREATE, "_create_ticket"),
    ],
)
async def test_conversation_write_action_requires_its_own_permission(
    session_factory, tenant_a, tenant_a_user, grant_permission, monkeypatch,
    action, permission, method,
):
    await grant_permission(tenant_a_user.id, Permission.CUSTOMER_CONSULT)
    scope = TenantScope(tenant_id=tenant_a.id, actor_id=tenant_a_user.id, actor_type="user")
    executor = ConversationActionExecutor(session_factory)
    operation = AsyncMock(return_value=ActionResult(action=action, summary="completed"))
    monkeypatch.setattr(executor, method, operation)
    decision = ActionDecision(action=action)

    denied = await executor.execute(
        scope=scope, decision=decision, user_message="test", thread_id="test-thread",
    )
    operation.assert_not_awaited()
    assert denied is not None and "权限" in denied.summary

    await grant_permission(tenant_a_user.id, permission)
    allowed = await executor.execute(
        scope=scope, decision=decision, user_message="test", thread_id="test-thread",
    )
    operation.assert_awaited_once()
    assert allowed is not None and allowed.summary == "completed"

    operation.reset_mock()
    async with session_factory() as session:
        user = await session.get(User, tenant_a_user.id)
        user.status = "disabled"
        await session.commit()
    denied = await executor.execute(
        scope=scope, decision=decision, user_message="test", thread_id="test-thread",
    )
    operation.assert_not_awaited()
    assert denied is not None and "权限" in denied.summary
