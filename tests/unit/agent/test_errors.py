from backend.agent.errors import FallbackPolicy, WorkflowError


def test_model_timeout_is_retryable_before_handoff() -> None:
    error = WorkflowError.from_exception("supervisor_agent", TimeoutError("timeout"))

    assert error.retryable is True
    assert FallbackPolicy.next_action(error, attempts=1) == "retry"
    assert FallbackPolicy.next_action(error, attempts=3) == "human_handoff"


def test_unknown_tool_state_goes_to_reconciliation() -> None:
    error = WorkflowError(
        error_code="unknown_tool_state",
        node_name="billing.execute",
        retryable=False,
        error_summary="third-party result is unknown",
    )

    assert FallbackPolicy.next_action(error, attempts=1) == "human_handoff"
