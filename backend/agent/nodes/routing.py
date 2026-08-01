from __future__ import annotations

from backend.agent.contracts import SUPPORTED_SUPERVISOR_ROUTES
from backend.agent.state import AgentState


def route_from_supervisor(state: AgentState) -> str:
    route = state.next_action
    if route not in SUPPORTED_SUPERVISOR_ROUTES:
        raise ValueError(f"unsupported route: {route}")
    return route


__all__ = ["route_from_supervisor"]
