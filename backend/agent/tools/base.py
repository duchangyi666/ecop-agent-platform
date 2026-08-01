from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    name: str
    owner_agent: str
    description: str


class ToolView:
    def __init__(self, tools: tuple[RegisteredTool, ...]) -> None:
        self._tools = tools

    def names(self) -> list[str]:
        return [tool.name for tool in self._tools]

    def get(self, name: str) -> RegisteredTool:
        for tool in self._tools:
            if tool.name == name:
                return tool
        raise KeyError(f"tool not registered for agent: {name}")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def for_agent(self, agent_name: str) -> ToolView:
        tools = tuple(tool for tool in self._tools.values() if tool.owner_agent == agent_name)
        return ToolView(tools)


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(RegisteredTool("billing.preview", "billing", "preview a refund request"))
    registry.register(RegisteredTool("billing.execute", "billing", "execute an approved refund request"))
    registry.register(RegisteredTool("knowledge.search", "knowledge", "search tenant knowledge"))
    registry.register(RegisteredTool("ticket.create", "ticket", "create a support ticket"))
    registry.register(RegisteredTool("ticket.update", "ticket", "update a support ticket"))
    registry.register(RegisteredTool("approval.request", "approval", "create an approval request"))
    registry.register(RegisteredTool("approval.status", "approval", "read approval status"))
    return registry


__all__ = ["RegisteredTool", "ToolRegistry", "ToolView", "build_default_tool_registry"]
