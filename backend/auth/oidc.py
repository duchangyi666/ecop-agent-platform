"""Minimal OIDC Authorization Code client for the local Dex IdP.

The backend acts as a BFF: the browser sends the authorization code + PKCE
verifier here, this module exchanges it with the IdP, verifies the ID token
signature/issuer/audience, and the API then issues its own short-lived JWT.
That keeps the client secret out of the browser and avoids token-endpoint CORS.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx
import jwt

from backend.auth.config import AuthSettings, get_auth_settings


class OIDCError(Exception):
    """Raised when the OIDC exchange or ID-token validation fails."""


@dataclass(frozen=True, slots=True)
class OIDCIdentity:
    subject: str
    email: str
    name: str
    tenant_slug: str


def _build_client(timeout: float) -> httpx.AsyncClient:
    # Same httpx 0.28 quirk as the model gateway: a bracketed IPv6 NO_PROXY
    # entry becomes an invalid "all://*[::1]" pattern.
    raw = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    if "[" in raw:
        cleaned = ",".join(
            part.strip() for part in raw.split(",") if part.strip() and "[" not in part
        )
        os.environ["NO_PROXY"] = cleaned
        os.environ["no_proxy"] = cleaned
    return httpx.AsyncClient(timeout=timeout)


class OIDCProvider:
    def __init__(
        self,
        settings: AuthSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not settings.oidc_configured:
            raise OIDCError("OIDC issuer/client credentials are not configured")
        self.settings = settings
        self._client = client or _build_client(settings.oidc_timeout_seconds)
        self._owns_client = client is None
        self._metadata: dict[str, Any] | None = None
        self._metadata_at = 0.0
        self._jwks: dict[str, Any] | None = None
        self._jwks_at = 0.0
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def metadata(self) -> dict[str, Any]:
        if self._metadata is not None and time.monotonic() - self._metadata_at < 300:
            return self._metadata
        async with self._lock:
            if self._metadata is not None and time.monotonic() - self._metadata_at < 300:
                return self._metadata
            url = f"{self.settings.oidc_issuer}/.well-known/openid-configuration"
            response = await self._client.get(url)
            if response.status_code != 200:
                raise OIDCError("OIDC discovery endpoint is unavailable")
            payload = response.json()
            if payload.get("issuer", "").rstrip("/") != self.settings.oidc_issuer:
                raise OIDCError("OIDC discovery issuer mismatch")
            self._metadata = payload
            self._metadata_at = time.monotonic()
            return payload

    async def jwks(self) -> dict[str, Any]:
        if self._jwks is not None and time.monotonic() - self._jwks_at < 300:
            return self._jwks
        metadata = await self.metadata()
        jwks_uri = metadata.get("jwks_uri")
        if not jwks_uri:
            raise OIDCError("OIDC discovery has no jwks_uri")
        response = await self._client.get(jwks_uri)
        if response.status_code != 200:
            raise OIDCError("OIDC JWKS endpoint is unavailable")
        payload = response.json()
        if not payload.get("keys"):
            raise OIDCError("OIDC JWKS contains no keys")
        self._jwks = payload
        self._jwks_at = time.monotonic()
        return payload

    async def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        metadata = await self.metadata()
        token_endpoint = metadata.get("token_endpoint")
        if not token_endpoint:
            raise OIDCError("OIDC discovery has no token_endpoint")
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or self.settings.oidc_redirect_uri,
            "client_id": self.settings.oidc_client_id,
            "client_secret": self.settings.oidc_client_secret,
            "code_verifier": code_verifier,
        }
        response = await self._client.post(token_endpoint, data=data)
        if response.status_code != 200:
            raise OIDCError("OIDC code exchange failed")
        payload = response.json()
        if not payload.get("id_token"):
            raise OIDCError("OIDC token response has no id_token")
        return payload

    async def verify_id_token(self, id_token: str) -> dict[str, Any]:
        jwks = await self.jwks()
        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.PyJWTError as exc:
            raise OIDCError("OIDC id_token header is invalid") from exc
        kid = header.get("kid")
        key = next(
            (item for item in jwks["keys"] if kid is None or item.get("kid") == kid),
            None,
        )
        if key is None:
            raise OIDCError("OIDC signing key not found")
        try:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
            return jwt.decode(
                id_token,
                key=public_key,
                algorithms=[key.get("alg", "RS256")],
                audience=self.settings.oidc_client_id,
                issuer=self.settings.oidc_issuer,
                options={
                    "require": ["exp", "iat", "iss", "aud", "sub"],
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise OIDCError("OIDC id_token validation failed") from exc

    async def authenticate(
        self,
        *,
        code: str,
        code_verifier: str,
        redirect_uri: str | None = None,
    ) -> OIDCIdentity:
        tokens = await self.exchange_code(
            code=code,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
        )
        claims = await self.verify_id_token(tokens["id_token"])
        email = str(claims.get("email") or claims.get("preferred_username") or "").strip()
        if not email:
            raise OIDCError("OIDC id_token has no email claim")
        tenant_slug = str(
            claims.get("tenant") or self.settings.oidc_default_tenant_slug
        ).strip()
        return OIDCIdentity(
            subject=str(claims["sub"]),
            email=email,
            name=str(claims.get("name") or email),
            tenant_slug=tenant_slug,
        )


@lru_cache(maxsize=1)
def get_oidc_provider() -> OIDCProvider:
    return OIDCProvider(get_auth_settings())


def reset_oidc_provider_cache() -> None:
    get_oidc_provider.cache_clear()


__all__ = [
    "OIDCError",
    "OIDCIdentity",
    "OIDCProvider",
    "get_oidc_provider",
    "reset_oidc_provider_cache",
]
