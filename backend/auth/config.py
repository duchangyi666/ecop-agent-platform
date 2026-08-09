from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field


class AuthSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    jwt_secret: str = Field(default="")
    token_expires_minutes: int = Field(default=60, ge=1, le=1440)


def get_auth_settings() -> AuthSettings:
    secret = os.getenv("JWT_SECRET", "").strip()
    auth_mode = os.getenv("AUTH_MODE", "dev").strip().lower()
    if auth_mode == "jwt-only" and not secret:
        raise RuntimeError("JWT_SECRET is required when AUTH_MODE=jwt-only")
    if secret and len(secret.encode("utf-8")) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 bytes")
    return AuthSettings(
        jwt_secret=secret,
        token_expires_minutes=int(os.getenv("JWT_TOKEN_EXPIRES_MINUTES", "60")),
    )


__all__ = ["AuthSettings", "get_auth_settings"]
