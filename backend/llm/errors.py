from __future__ import annotations

from backend.llm.contracts import ModelCallError


class ModelGatewayError(RuntimeError):
    def __init__(self, error: ModelCallError) -> None:
        super().__init__(error.safe_message)
        self.error = error


__all__ = ["ModelGatewayError"]
