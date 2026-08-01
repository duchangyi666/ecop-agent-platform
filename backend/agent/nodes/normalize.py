from __future__ import annotations

from backend.agent.state import AgentState


def normalize_request(state: AgentState) -> dict[str, object]:
    if not state.conversation:
        raise ValueError("conversation cannot be empty")
    return {}


__all__ = ["normalize_request"]
