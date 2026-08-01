from __future__ import annotations

from decimal import Decimal

import pytest

from backend.agent.policies.risk import RefundPolicyContext, evaluate_refund_policy
from backend.agent.tools.base import build_default_tool_registry


@pytest.mark.asyncio
async def test_refund_workflow_contract_separates_preview_execution_and_policy() -> None:
    registry = build_default_tool_registry()
    preview_tool = registry.for_agent("billing").get("billing.preview")
    execute_tool = registry.for_agent("billing").get("billing.execute")
    decision = evaluate_refund_policy(
        RefundPolicyContext(
            amount=Decimal("5000.00"),
            payment_amount=Decimal("6000.00"),
            actor_type="user",
            payment_status="succeeded",
            has_unknown_execution=False,
        )
    )

    assert preview_tool.name == "billing.preview"
    assert execute_tool.name == "billing.execute"
    assert decision.requires_approval is True
