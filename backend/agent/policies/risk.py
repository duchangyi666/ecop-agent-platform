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


_OFFLINE_BILLING_CONTENT = "billing context and refund preview are required"
_APPROVAL_HANDOFF = "当前退款请求需要人工审批后才能继续，已为您转交审核。"


def policy_gate_node(state: AgentState) -> dict[str, object]:
    specialist = state.specialist_result
    if specialist is not None and specialist.status == "needs_policy_gate":
        # Offline billing has no approval summary. A live refund that opened an
        # approval keeps that customer-safe summary as the handoff reply.
        content = (specialist.content or "").strip()
        final_response = content if content and content != _OFFLINE_BILLING_CONTENT else _APPROVAL_HANDOFF
        return {
            "status": "human_handoff",
            "next_action": "human_handoff",
            "final_response": final_response,
        }
    return {"next_action": "finish"}


__all__ = [
    "HIGH_RISK_REFUND_THRESHOLD",
    "PolicyDecision",
    "RefundPolicyContext",
    "evaluate_refund_policy",
    "policy_gate_node",
]
