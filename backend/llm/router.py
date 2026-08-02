from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class ModelTask(str, Enum):
    CUSTOMER_SERVICE = "customer_service"
    KNOWLEDGE = "knowledge"
    TICKET = "ticket"
    BILLING = "billing"


@dataclass(frozen=True, slots=True)
class ModelRoute:
    task: ModelTask
    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout_seconds: float = 30.0
    max_retries: int = 1


class ModelRouter:
    def __init__(self, routes: dict[ModelTask, ModelRoute]) -> None:
        self.routes = routes

    def resolve(self, task: ModelTask) -> ModelRoute:
        try:
            return self.routes[task]
        except KeyError as exc:
            raise ValueError(f"no model route for task: {task}") from exc


def create_default_model_router() -> ModelRouter:
    default_model = os.getenv("MODEL_ROUTE_MODEL", "deepseek-v4-flash")
    routes = {
        task: ModelRoute(
            task=task,
            provider=os.getenv("MODEL_ROUTE_PROVIDER", "deepseek"),
            model=os.getenv(
                f"MODEL_ROUTE_{task.name}_MODEL",
                default_model,
            ),
            temperature=float(os.getenv("MODEL_ROUTE_TEMPERATURE", "0")),
            max_tokens=int(os.getenv("MODEL_ROUTE_MAX_TOKENS", "1024")),
            timeout_seconds=float(os.getenv("MODEL_ROUTE_TIMEOUT_SECONDS", "30")),
            max_retries=int(os.getenv("MODEL_ROUTE_MAX_RETRIES", "1")),
        )
        for task in ModelTask
    }
    return ModelRouter(routes)


__all__ = ["ModelRoute", "ModelRouter", "ModelTask", "create_default_model_router"]
