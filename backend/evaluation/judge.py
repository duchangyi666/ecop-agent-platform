from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.llm.gateway import ModelGateway

JUDGE_SYSTEM_PROMPT = (
    "你是一位资深客服质检专家。请判断 Agent 的回答与标准答案在语义上是否一致："
    "允许措辞不同，但核心事实与结论必须一致。只输出 JSON，不要输出其他内容。"
)


class AnswerVerdict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: Literal["correct", "incorrect"]
    reason: str = Field(default="", max_length=300)


class AnswerJudge:
    """LLM-as-a-Judge for answer correctness.

    Compares the agent's generated answer against the gold answer using the
    application ModelGateway. A failed judge call returns None so the runner
    can record it and conservatively mark the case as incorrect instead of
    crashing the whole evaluation run.
    """

    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    async def judge(
        self,
        *,
        question: str,
        gold_answer: str,
        agent_answer: str,
    ) -> AnswerVerdict | None:
        user_prompt = (
            f"用户问题：{question}\n"
            f"标准答案：{gold_answer}\n"
            f"Agent 回答：{agent_answer}\n\n"
            "请判断 Agent 回答与标准答案是否语义一致，"
            "输出 verdict（correct 或 incorrect）和一句简短理由。"
        )
        try:
            draft, _ = await self.gateway.generate_structured(
                system_prompt=JUDGE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=AnswerVerdict,
            )
            if isinstance(draft, AnswerVerdict):
                return draft
            return AnswerVerdict.model_validate(draft.model_dump())
        except Exception:
            return None


__all__ = ["AnswerJudge", "AnswerVerdict", "JUDGE_SYSTEM_PROMPT"]
