from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt

from backend.auth.config import get_auth_settings


class InvalidToken(Exception):
    pass


@dataclass(frozen=True, slots=True)
class TokenClaims:
    tenant_id: UUID
    user_id: UUID
    actor_type: str
    token_id: str
    expires_at: datetime


def create_access_token(
    *,
    tenant_id: UUID,
    user_id: UUID,
    actor_type: str,
    secret: str | None = None,
    expires_minutes: int | None = None,
) -> str:
    settings = get_auth_settings()
    resolved_secret = secret if secret is not None else settings.jwt_secret
    if not resolved_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    now = datetime.now(timezone.utc)
    expires_delta = timedelta(
        minutes=expires_minutes or settings.token_expires_minutes
    )
    payload = {
        "iss": "clouddesk-local",
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "actor_type": actor_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, resolved_secret, algorithm="HS256")


def decode_access_token(
    token: str,
    secret: str | None = None,
) -> TokenClaims:
    settings = get_auth_settings()
    resolved_secret = secret if secret is not None else settings.jwt_secret
    if not resolved_secret:
        raise InvalidToken("JWT_SECRET is not configured")
    try:
        payload = jwt.decode(
            token,
            resolved_secret,
            algorithms=["HS256"],
            options={
                "require": ["sub", "tenant_id", "actor_type", "exp", "iat", "jti"],
            },
        )
    except jwt.PyJWTError as exc:
        raise InvalidToken("invalid or expired access token") from exc

    try:
        tenant_id = UUID(payload["tenant_id"])
        user_id = UUID(payload["sub"])
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidToken("invalid access token claims") from exc
    return TokenClaims(
        tenant_id=tenant_id,
        user_id=user_id,
        actor_type=str(payload["actor_type"]),
        token_id=str(payload["jti"]),
        expires_at=expires_at,
    )


__all__ = ["InvalidToken", "TokenClaims", "create_access_token", "decode_access_token"]
