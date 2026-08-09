from __future__ import annotations

from uuid import uuid4

import pytest

from backend.agent.agents.customer_service import build_customer_service_graph
from backend.agent.state import KnowledgeEvidence, create_agent_state
from backend.database.base import TenantScope
from backend.llm.contracts import ModelUsage, ResponseDraft


class RecordingModelGateway:
    def __init__(self, draft: ResponseDraft) -> None:
        self.draft = draft
        self.system_prompt = ""

    async def generate_structured(self, *, system_prompt, user_prompt, response_model):
        del user_prompt
        self.system_prompt = system_prompt
        return response_model.model_validate(self.draft.model_dump()), ModelUsage(
            provider="recording",
            model="recording",
            latency_ms=0,
        )

    def generate_stream(self, *, system_prompt, user_prompt):
        del user_prompt
        self.system_prompt = system_prompt

        async def _stream():
            yield self.draft.answer

        return _stream()


def _state(message: str, *, evidence: list[KnowledgeEvidence]):
    return create_agent_state(
        scope=TenantScope(tenant_id=uuid4()),
        request_id=uuid4(),
        message=message,
    ).model_copy(update={"knowledge_evidence": evidence})


@pytest.mark.asyncio
async def test_customer_service_prompt_includes_retrieved_knowledge_evidence() -> None:
    evidence = [
        KnowledgeEvidence(
            document_id=uuid4(),
            external_document_id="refund-policy",
            title="退款政策",
            source_uri="https://docs.example.com/refund-policy",
            content_snippet="同一账单在二十四小时内重复扣费可以申请退款。",
            score=0.95,
        )
    ]
    gateway = RecordingModelGateway(
        ResponseDraft(
            answer="根据退款政策，重复扣费可以申请退款。",
            next_action="finish",
            confidence=0.9,
        )
    )

    result = await build_customer_service_graph(
        model_gateway=gateway,
    ).compile().ainvoke(_state("客户咨询一般说明", evidence=evidence))

    assert "可用知识依据" in gateway.system_prompt
    assert "退款政策" in gateway.system_prompt
    assert "同一账单在二十四小时内重复扣费可以申请退款。" in gateway.system_prompt
    assert result["final_response"] == "根据退款政策，重复扣费可以申请退款。"
    assert result["response_review"].status == "allow"


@pytest.mark.asyncio
async def test_customer_service_safety_filter_accepts_evidence_grounded_claim() -> None:
    evidence = [
        KnowledgeEvidence(
            document_id=uuid4(),
            external_document_id="refund-policy",
            title="退款政策",
            content_snippet="低风险重复扣费可以自动退款。",
            score=0.9,
        )
    ]
    gateway = RecordingModelGateway(
        ResponseDraft(
            answer="根据政策，退款已完成。",
            next_action="finish",
            confidence=0.9,
        )
    )

    result = await build_customer_service_graph(
        model_gateway=gateway,
    ).compile().ainvoke(_state("客户咨询一般说明", evidence=evidence))

    assert result["response_review"].status == "allow"
    assert result["final_response"] == "根据政策，退款已完成。"
