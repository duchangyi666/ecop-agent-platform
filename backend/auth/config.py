from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AuthMode = Literal["dev", "jwt-only", "oidc"]


class AuthSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    jwt_secret: str = Field(default="")
    token_expires_minutes: int = Field(default=60, ge=1, le=1440)
    auth_mode: AuthMode = "dev"
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = "http://localhost:3000/auth/callback"
    oidc_allowed_redirect_uris: str = (
        "http://localhost:3000/auth/callback,http://127.0.0.1:3000/auth/callback"
    )
    oidc_default_tenant_slug: str = "clouddesk"
    oidc_scopes: str = "openid profile email"
    oidc_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    @property
    def oidc_configured(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret)

    @property
    def oidc_allowed_redirects(self) -> set[str]:
        return {
            item.strip().rstrip("/")
            for item in self.oidc_allowed_redirect_uris.split(",")
            if item.strip()
        }


def _auth_mode() -> AuthMode:
    raw = os.getenv("AUTH_MODE", "dev").strip().lower()
    if raw not in {"dev", "jwt-only", "oidc"}:
        raise ValueError(f"unsupported AUTH_MODE: {raw}")
    return raw  # type: ignore[return-value]


def get_auth_settings() -> AuthSettings:
    return AuthSettings(
        jwt_secret=os.getenv("JWT_SECRET", "").strip(),
        token_expires_minutes=int(os.getenv("JWT_TOKEN_EXPIRES_MINUTES", "60")),
        auth_mode=_auth_mode(),
        oidc_issuer=os.getenv("OIDC_ISSUER", "").strip().rstrip("/"),
        oidc_client_id=os.getenv("OIDC_CLIENT_ID", "").strip(),
        oidc_client_secret=os.getenv("OIDC_CLIENT_SECRET", "").strip(),
        oidc_redirect_uri=os.getenv(
            "OIDC_REDIRECT_URI", "http://localhost:3000/auth/callback"
        ).strip(),
        oidc_allowed_redirect_uris=os.getenv(
            "OIDC_ALLOWED_REDIRECT_URIS",
            "http://localhost:3000/auth/callback,http://127.0.0.1:3000/auth/callback",
        ).strip(),
        oidc_default_tenant_slug=os.getenv("OIDC_DEFAULT_TENANT_SLUG", "clouddesk").strip()
        or "clouddesk",
        oidc_scopes=os.getenv("OIDC_SCOPES", "openid profile email").strip(),
        oidc_timeout_seconds=float(os.getenv("OIDC_TIMEOUT_SECONDS", "10")),
    )


__all__ = ["AuthMode", "AuthSettings", "get_auth_settings"]

