from __future__ import annotations

import pytest

from backend.evaluation.judge import AnswerJudge, AnswerVerdict
from backend.llm.fake import FakeModelGateway


@pytest.mark.asyncio
async def test_judge_returns_correct_verdict() -> None:
    gateway = FakeModelGateway(AnswerVerdict(verdict="correct", reason="语义一致"))
    judge = AnswerJudge(gateway)
    verdict = await judge.judge(
        question="退款多久到账？",
        gold_answer="1-3 个工作日",
        agent_answer="退款审批通过后 1-3 个工作日到账",
    )
    assert verdict is not None
    assert verdict.verdict == "correct"


@pytest.mark.asyncio
async def test_judge_returns_none_on_gateway_failure() -> None:
    gateway = FakeModelGateway(RuntimeError("provider down"))
    judge = AnswerJudge(gateway)
    verdict = await judge.judge(
        question="q",
        gold_answer="a",
        agent_answer="b",
    )
    assert verdict is None


@pytest.mark.asyncio
async def test_judge_treats_invalid_output_as_none() -> None:
    # A non-AnswerVerdict response cannot be validated into the verdict model.
    from backend.llm.contracts import ResponseDraft

    gateway = FakeModelGateway(
        ResponseDraft(answer="not a verdict", next_action="finish", confidence=0.5)
    )
    judge = AnswerJudge(gateway)
    verdict = await judge.judge(
        question="q",
        gold_answer="a",
        agent_answer="b",
    )
    assert verdict is None
