from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ModelGatewaySettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    api_key: SecretStr | None = None
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    max_retries: int = Field(default=1, ge=0, le=2)

    @classmethod
    def from_env(cls) -> "ModelGatewaySettings":
        raw_timeout = os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "30")
        raw_retries = os.getenv("DEEPSEEK_MAX_RETRIES", "1")
        return cls(
            api_key=SecretStr(os.environ["DEEPSEEK_API_KEY"])
            if os.getenv("DEEPSEEK_API_KEY")
            else None,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            timeout_seconds=float(raw_timeout),
            max_retries=int(raw_retries),
        )


__all__ = ["ModelGatewaySettings"]
