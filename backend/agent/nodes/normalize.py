from __future__ import annotations

from backend.agent.state import AgentState


def normalize_request(state: AgentState) -> dict[str, object]:
    if not state.conversation or not any(
        message.role == "user" and message.content.strip() for message in state.conversation
    ):
        raise ValueError("conversation cannot be empty")
    return {}


__all__ = ["normalize_request"]
