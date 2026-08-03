from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.agent.contracts import SupervisorDecision
from backend.agent.state import AgentState
from backend.llm.gateway import ModelGateway

_ROUTE_SYSTEM_PROMPT = (
    "你是 CloudDesk 客服的路由主管。结合对话历史判断当前应交给哪个专家，只输出 JSON。"
    "route 取值：route_billing(退款/扣费/支付/账单类业务办理或查询)、"
    "route_ticket(工单创建或工单进度)、route_approval(审批进度/审批相关)、"
    "route_knowledge(纯政策/知识咨询)、route_customer(一般对话/问候/其他)。"
)


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    route: Literal[
        "route_billing",
        "route_ticket",
        "route_approval",
        "route_knowledge",
        "route_customer",
    ] = "route_customer"


def keyword_route(state: AgentState) -> str:
    """Deterministic fallback router (also used when the LLM is unavailable)."""
    message = state.conversation[-1].content.lower() if state.conversation else ""
    # If a business action was already executed, answer via customer service.
    if any(
        (item.external_document_id or "").startswith("action-")
        for item in state.knowledge_evidence
    ):
        return "route_customer"
    if any(k in message for k in ("如何", "怎么", "是什么", "政策", "规则", "为什么", "能否", "可以吗")):
        return "route_customer"
    if any(k in message for k in ("退款", "退费", "refund", "账单", "支付", "扣费")):
        return "route_billing"
    if any(k in message for k in ("工单", "投诉", "故障")):
        return "route_ticket"
    if any(k in message for k in ("审批", "审核", "approval")):
        return "route_approval"
    return "route_customer"


async def llm_route(gateway: ModelGateway, state: AgentState) -> str:
    lines = []
    for message in state.conversation:
        speaker = "用户" if message.role == "user" else "客服"
        lines.append(f"{speaker}：{message.content}")
    try:
        decision, _ = await gateway.generate_structured(
            system_prompt=_ROUTE_SYSTEM_PROMPT,
            user_prompt="\n".join(lines),
            response_model=RouteDecision,
        )
        return decision.route
    except Exception:
        return keyword_route(state)


def make_supervisor_node(gateway: ModelGateway | None = None):
    """Return a supervisor node. With a gateway it routes via the LLM,
    falling back to the deterministic keyword router."""

    async def supervisor_node(state: AgentState) -> dict[str, object]:
        if gateway is not None:
            route = await llm_route(gateway, state)
        else:
            route = keyword_route(state)
        decision = SupervisorDecision(route=route, reason="supervisor routing")
        return {"supervisor_decision": decision, "next_action": decision.route}

    return supervisor_node


def supervisor_node(state: AgentState) -> dict[str, object]:
    """Synchronous keyword-based node kept for tests / LLM-less graphs."""
    route = keyword_route(state)
    decision = SupervisorDecision(route=route, reason="keyword-based structural router")
    return {"supervisor_decision": decision, "next_action": decision.route}


__all__ = [
    "RouteDecision",
    "keyword_route",
    "llm_route",
    "make_supervisor_node",
    "supervisor_node",
]
