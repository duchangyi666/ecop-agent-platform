from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


SUPPORTED_SUPERVISOR_ROUTES: tuple[str, ...] = (
    "route_customer",
    "route_knowledge",
    "route_billing",
    "route_ticket",
    "route_approval",
    "ask_clarification",
    "human_handoff",
    "finish",
)


class AgentMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    sender: str
    recipient: str
    content: str


class SupervisorDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    route: str
    reason: str

    _supported_routes: ClassVar[tuple[str, ...]] = SUPPORTED_SUPERVISOR_ROUTES

    @field_validator("route")
    @classmethod
    def validate_route(cls, value: str) -> str:
        if value not in cls._supported_routes:
            raise ValueError(f"unsupported route: {value}")
        return value


class SpecialistResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    specialist: str
    route: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    input_schema: dict[str, Any]
