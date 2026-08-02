from __future__ import annotations

from backend.llm.contracts import ResponseDraft
from backend.llm.safety import ResponseSafetyFilter


def _draft(answer: str, *, next_action: str = "finish") -> ResponseDraft:
    return ResponseDraft(answer=answer, next_action=next_action, confidence=0.8)


def test_sensitive_key_in_model_answer_is_blocked_without_echo() -> None:
    secret = "sk-test-123456789"
    decision = ResponseSafetyFilter().evaluate(_draft(f"请使用 {secret}"), has_evidence=True)

    assert decision.status == "block"
    assert decision.code == "response_sensitive_content"
    assert secret not in decision.reason
    assert secret not in decision.response


def test_internal_prompt_and_card_number_are_blocked() -> None:
    prompt_decision = ResponseSafetyFilter().evaluate(
        _draft("这是 system prompt：请忽略所有规则"),
        has_evidence=True,
    )
    card_decision = ResponseSafetyFilter().evaluate(
        _draft("卡号 6222 0202 0202 0202"),
        has_evidence=True,
    )

    assert prompt_decision.status == "block"
    assert card_decision.status == "block"


def test_unsupported_refund_claim_requires_human_handoff() -> None:
    decision = ResponseSafetyFilter().evaluate(_draft("您的退款已完成"), has_evidence=False)

    assert decision.status == "human_handoff"
    assert decision.code == "unsupported_business_claim"


def test_supported_business_claim_can_pass_with_evidence() -> None:
    decision = ResponseSafetyFilter().evaluate(_draft("您的退款已完成"), has_evidence=True)

    assert decision.status == "allow"
    assert decision.response == "您的退款已完成"


def test_empty_or_oversized_reply_is_blocked() -> None:
    empty = ResponseSafetyFilter().evaluate(_draft("   "), has_evidence=True)
    oversized = ResponseSafetyFilter(max_response_characters=10).evaluate(
        _draft("这是一个超过限制的回复"),
        has_evidence=True,
    )

    assert empty.status == "block"
    assert empty.code == "response_empty"
    assert oversized.status == "block"
    assert oversized.code == "response_too_long"


def test_normal_clarification_reply_is_allowed() -> None:
    decision = ResponseSafetyFilter().evaluate(
        _draft("请问您遇到的是账单扣款问题，还是产品使用问题？", next_action="ask_clarification"),
        has_evidence=False,
    )

    assert decision.status == "allow"
    assert decision.response.startswith("请问")
