from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from backend.agent.state import AgentState


HIGH_RISK_REFUND_THRESHOLD = Decimal("1000.00")


class RefundPolicyContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: Decimal
    payment_amount: Decimal
    actor_type: str
    payment_status: str
    has_unknown_execution: bool


class PolicyDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: bool
    requires_approval: bool
    reason: str


def evaluate_refund_policy(context: RefundPolicyContext) -> PolicyDecision:
    if context.has_unknown_execution:
        return PolicyDecision(
            allowed=False,
            requires_approval=False,
            reason="unknown execution state requires reconciliation",
        )
    if context.payment_status != "succeeded":
        return PolicyDecision(allowed=False, requires_approval=False, reason="payment is not succeeded")
    if context.amount <= Decimal("0.00") or context.amount > context.payment_amount:
        return PolicyDecision(allowed=False, requires_approval=False, reason="refund amount is invalid")

    requires_approval = context.amount >= HIGH_RISK_REFUND_THRESHOLD or context.actor_type != "user"
    return PolicyDecision(
        allowed=True,
        requires_approval=requires_approval,
        reason="high risk refund requires approval" if requires_approval else "low risk refund can execute",
    )


def policy_gate_node(state: AgentState) -> dict[str, object]:
    if state.specialist_result is not None and state.specialist_result.status == "needs_policy_gate":
        return {"next_action": "human_handoff"}
    return {"next_action": "finish"}


__all__ = [
    "HIGH_RISK_REFUND_THRESHOLD",
    "PolicyDecision",
    "RefundPolicyContext",
    "evaluate_refund_policy",
    "policy_gate_node",
]
