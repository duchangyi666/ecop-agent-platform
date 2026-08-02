from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field


class AuthSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    jwt_secret: str = Field(default="")
    token_expires_minutes: int = Field(default=60, ge=1, le=1440)


def get_auth_settings() -> AuthSettings:
    return AuthSettings(
        jwt_secret=os.getenv("JWT_SECRET", "").strip(),
        token_expires_minutes=int(os.getenv("JWT_TOKEN_EXPIRES_MINUTES", "60")),
    )


__all__ = ["AuthSettings", "get_auth_settings"]
