from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.llm.contracts import ResponseDraft


class ResponseSafetyDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["allow", "block", "human_handoff"]
    code: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=160)
    response: str = Field(min_length=1, max_length=2000)


class ResponseSafetyFilter:
    _credential_patterns = (
        re.compile(r"\bsk-[a-z0-9][a-z0-9_-]{7,}\b"),
        re.compile(r"\bbearer\s+[a-z0-9._-]{8,}\b"),
        re.compile(r"(?:api[\s_-]?key|password|passwd|secret|token)\s*[:=]\s*\S+"),
        re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
    )
    _internal_patterns = (
        "system prompt",
        "系统提示词",
        "系统提示",
        "内部规则",
        "数据库地址",
        "postgresql://",
        "postgres://",
    )
    _unsupported_claims = (
        "退款已完成",
        "退款已经完成",
        "支付已到账",
        "支付成功",
        "审批已通过",
        "审批通过",
    )

    def __init__(self, *, max_response_characters: int = 2000) -> None:
        if max_response_characters < 1:
            raise ValueError("max_response_characters must be positive")
        self.max_response_characters = max_response_characters

    def evaluate(self, draft: ResponseDraft, *, has_evidence: bool) -> ResponseSafetyDecision:
        answer = draft.answer.strip()
        normalized = unicodedata.normalize("NFKC", answer).casefold()
        if not answer:
            return ResponseSafetyDecision(
                status="block",
                code="response_empty",
                reason="模型回复为空",
                response="当前回复内容为空，请转人工处理。",
            )
        if len(answer) > self.max_response_characters:
            return ResponseSafetyDecision(
                status="block",
                code="response_too_long",
                reason="模型回复超过安全长度",
                response="当前回复内容过长，请转人工处理。",
            )
        if any(pattern.search(normalized) for pattern in self._credential_patterns) or any(
            pattern in normalized for pattern in self._internal_patterns
        ):
            return ResponseSafetyDecision(
                status="block",
                code="response_sensitive_content",
                reason="模型回复包含不允许公开的信息",
                response="抱歉，我无法提供内部配置、凭据或未经授权的数据。",
            )
        if not has_evidence and any(claim in normalized for claim in self._unsupported_claims):
            return ResponseSafetyDecision(
                status="human_handoff",
                code="unsupported_business_claim",
                reason="业务结论缺少已验证依据",
                response="该业务结果需要基于已验证信息并由人工确认。",
            )
        return ResponseSafetyDecision(
            status="allow",
            code="response_allowed",
            reason="回复安全检查通过",
            response=answer,
        )


__all__ = ["ResponseSafetyDecision", "ResponseSafetyFilter"]
