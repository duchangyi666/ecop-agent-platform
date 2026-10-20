from __future__ import annotations

from collections.abc import Sequence
import json
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.agent.contracts import SpecialistResult
from backend.agent.nodes.guards import domain_guard_node, input_security_guard_node
from backend.agent.state import AgentState, ConversationMessage, KnowledgeEvidence
from backend.llm.contracts import ResponseDraft
from backend.llm.context import ContextBudget, truncate_text
from backend.llm.errors import ModelGatewayError
from backend.llm.fake import FakeModelGateway
from backend.llm.gateway import ModelGateway
from backend.llm.prompt_registry import PromptRegistry, create_default_prompt_registry
from backend.llm.safety import ResponseSafetyFilter


_MODEL_ERROR_RESPONSE = "当前智能回复服务暂时不可用，将为您转人工处理。"
_DEFAULT_OFFLINE_RESPONSE = (
    "您好，我可以协助处理 CloudDesk 账户、账单、产品支持和工单问题。"
    "请描述您需要办理的事项。"
)


def _default_offline_gateway() -> FakeModelGateway:
    """Return a deterministic gateway so local startup never requires a model key."""

    return FakeModelGateway(
        ResponseDraft(
            answer=_DEFAULT_OFFLINE_RESPONSE,
            next_action="ask_clarification",
            confidence=0.5,
        )
    )


def _last_user_message(state: AgentState) -> str:
    for message in reversed(state.conversation):
        if message.role == "user":
            return message.content
    return ""


def _extract_reply_text(value: Any) -> str:
    """Unwrap common JSON/code-fence model responses before safety review."""

    if isinstance(value, dict):
        for key in ("answer", "response", "content", "text"):
            if value.get(key):
                return str(value[key]).strip()
        return json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json|text)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(parsed, dict):
        return _extract_reply_text(parsed)
    return str(parsed).strip()


def _status_for_next_action(next_action: str) -> str:
    if next_action == "human_handoff":
        return "human_handoff"
    if next_action == "ask_clarification":
        return "needs_clarification"
    return "completed"


def _customer_service_preflight(state: AgentState) -> tuple[dict[str, Any], bool]:
    """Run guards for direct customer-service graph calls as well as main-graph calls."""

    updates: dict[str, Any] = {}
    guard = state.guard_decision
    if guard is None:
        guard = input_security_guard_node(state)["guard_decision"]
        updates["guard_decision"] = guard
    if guard.status != "allow":
        status = "blocked" if guard.status == "block" else "human_handoff"
        message = _FRIENDLY_REFUSAL if status == "blocked" else "该操作需要人工安全审核。"
        updates.update(
            {
                "final_response": message,
                "status": status,
                "next_action": "finish" if status == "blocked" else "human_handoff",
                "response_review": None,
            }
        )
        return updates, True

    domain = state.domain_decision
    if domain is None:
        domain = domain_guard_node(state)["domain_decision"]
        updates["domain_decision"] = domain
    if domain.status != "in_scope":
        message = (
            "请补充具体业务场景。"
            if domain.status == "needs_clarification"
            else "请求超出当前平台支持范围。"
        )
        updates.update(
            {
                "final_response": message,
                "status": "needs_clarification" if domain.status == "needs_clarification" else "out_of_scope",
                "next_action": "ask_clarification" if domain.status == "needs_clarification" else "finish",
                "response_review": None,
            }
        )
        return updates, True
    return updates, False


def _prompt_messages(
    conversation: Sequence[ConversationMessage],
    knowledge_evidence: Sequence[KnowledgeEvidence] | None = None,
    prompt_registry: PromptRegistry | None = None,
    context_budget: ContextBudget | None = None,
) -> tuple[str, str]:
    registry = prompt_registry or create_default_prompt_registry()
    budget = context_budget or ContextBudget()
    system_prompt = registry.get("customer_service").template
    if knowledge_evidence:
        evidence_lines: list[str] = []
        used_characters = 0
        for item in knowledge_evidence:
            line = f"[{item.document_id}] {item.title}: {item.content_snippet or ''}"
            if used_characters + len(line) > budget.max_evidence_characters:
                break
            evidence_lines.append(line)
            used_characters += len(line)
        system_prompt += (
            "\n\n可用知识依据（回答必须依据这些内容，未在依据中出现的业务结论不能声称）：\n"
            + "\n".join(evidence_lines)
        )
    # Reconstruct the prior dialogue so the model answers with full context.
    history_lines: list[str] = []
    for message in conversation:
        speaker = "用户" if message.role == "user" else "客服"
        history_lines.append(f"{speaker}：{message.content}")
    user_prompt = "\n".join(history_lines)
    return truncate_text(system_prompt, budget.max_system_characters), truncate_text(
        user_prompt, budget.max_context_characters
    )


async def _customer_service_model_node(
    state: AgentState,
    *,
    model_gateway: ModelGateway,
) -> dict[str, Any]:
    system_prompt, user_prompt = _prompt_messages(
        state.conversation,
        knowledge_evidence=state.knowledge_evidence,
    )
    next_call_count = state.model_call_count + 1

    try:
        draft_value, usage = await model_gateway.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=ResponseDraft,
        )
        draft = ResponseDraft.model_validate(draft_value)
    except ModelGatewayError as exc:
        return {
            "model_error": exc.error,
            "model_call_count": next_call_count,
            "final_response": _MODEL_ERROR_RESPONSE,
            "status": "human_handoff",
            "next_action": "human_handoff",
            "specialist_result": SpecialistResult(
                specialist="customer_service",
                route="route_customer",
                content=_MODEL_ERROR_RESPONSE,
                status="human_handoff",
                metadata={"model_error_code": exc.error.code},
            ),
        }

    return {
        "response_draft": draft,
        "model_usage": usage,
        "model_call_count": next_call_count,
        "total_input_tokens": state.total_input_tokens + (usage.input_tokens or 0),
        "total_output_tokens": state.total_output_tokens + (usage.output_tokens or 0),
        "status": _status_for_next_action(draft.next_action),
        "next_action": draft.next_action,
        "specialist_result": SpecialistResult(
            specialist="customer_service",
            route="route_customer",
            content=draft.answer,
            metadata={"next_action": draft.next_action},
        ),
    }


def _response_safety_filter_node(state: AgentState) -> dict[str, Any]:
    if state.response_draft is None:
        return {}

    decision = ResponseSafetyFilter().evaluate(
        state.response_draft,
        has_evidence=bool(state.response_draft.evidence_ids or state.knowledge_evidence),
    )
    result: dict[str, Any] = {
        "response_review": decision,
        "final_response": decision.response,
    }
    if decision.status != "allow":
        result["status"] = "human_handoff"
        result["next_action"] = "human_handoff"
        result["specialist_result"] = SpecialistResult(
            specialist="customer_service",
            route="route_customer",
            content=decision.response,
            status="human_handoff",
            metadata={"response_review_code": decision.code},
        )
    else:
        result["status"] = _status_for_next_action(state.next_action)
    return result


_FRIENDLY_REFUSAL = (
    "抱歉，我无法协助获取系统配置、内部提示、凭据或未经授权的数据。"
    "我可以继续帮助您处理 CloudDesk 账户、账单、产品支持和工单相关问题。"
)


async def stream_customer_answer(
    state: AgentState,
    model_gateway: ModelGateway,
    event_sink=None,
) -> dict[str, Any]:
    """Guards + grounded prompt + true token streaming + safety filter.

    Used as the LangGraph customer-service node so orchestration stays in-graph.
    Returns the state updates consumed by the parent graph.
    """
    thread_id = str(state.request_id)
    preflight, terminal = _customer_service_preflight(state)
    if terminal:
        return preflight

    system_prompt, user_prompt = _prompt_messages(
        state.conversation, knowledge_evidence=state.knowledge_evidence
    )
    accumulated: list[str] = []
    try:
        async for token in model_gateway.generate_stream(
            system_prompt=system_prompt, user_prompt=user_prompt
        ):
            accumulated.append(token)
            if event_sink is not None:
                await event_sink("token", {"thread_id": thread_id, "text": token})
    except ModelGatewayError as exc:
        return {
            **preflight,
            "model_error": exc.error,
            "model_call_count": state.model_call_count + 1,
            "final_response": _MODEL_ERROR_RESPONSE,
            "status": "human_handoff",
            "next_action": "human_handoff",
            "response_review": None,
        }
    text = _extract_reply_text("".join(accumulated)) or "抱歉，我暂时无法生成回复，请稍后再试或联系人工客服。"
    draft = ResponseDraft(answer=text, next_action="finish", confidence=0.8)
    decision = ResponseSafetyFilter().evaluate(
        draft, has_evidence=bool(state.knowledge_evidence)
    )
    if decision.status != "allow":
        return {
            **preflight,
            "response_draft": draft,
            "final_response": decision.response,
            "status": "human_handoff",
            "next_action": "human_handoff",
            "response_review": decision,
            "model_call_count": state.model_call_count + 1,
            "specialist_result": SpecialistResult(
                specialist="customer_service",
                route="route_customer",
                content=decision.response,
                status="human_handoff",
                metadata={"response_review_code": decision.code},
            ),
        }
    return {
        **preflight,
        "response_draft": draft,
        "final_response": decision.response,
        "status": "completed",
        "next_action": "finish",
        "response_review": decision,
        "model_call_count": state.model_call_count + 1,
        "specialist_result": SpecialistResult(
            specialist="customer_service",
            route="route_customer",
            content=decision.response,
            metadata={"next_action": "finish"},
        ),
    }


def build_customer_service_graph(
    model_gateway: ModelGateway | None = None,
    event_sink=None,
) -> StateGraph:
    """Customer-service subgraph with a structured path and an optional streaming path."""
    gateway = model_gateway or _default_offline_gateway()

    async def customer_service_structured_node(state: AgentState) -> dict[str, Any]:
        preflight, terminal = _customer_service_preflight(state)
        if terminal:
            return preflight
        return {**preflight, **await _customer_service_model_node(state, model_gateway=gateway)}

    async def customer_service_stream_node(state: AgentState) -> dict[str, Any]:
        return await stream_customer_answer(state, gateway, event_sink)

    graph = StateGraph(AgentState)
    if event_sink is None:
        graph.add_node("customer_service_model", customer_service_structured_node)
        graph.add_node("response_safety_filter", _response_safety_filter_node)
        graph.add_edge(START, "customer_service_model")
        graph.add_edge("customer_service_model", "response_safety_filter")
        graph.add_edge("response_safety_filter", END)
    else:
        graph.add_node("customer_service_stream", customer_service_stream_node)
        graph.add_edge(START, "customer_service_stream")
        graph.add_edge("customer_service_stream", END)
    return graph


__all__ = ["build_customer_service_graph"]
