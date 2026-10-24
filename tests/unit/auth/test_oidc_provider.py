from __future__ import annotations

import base64
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.auth.config import AuthSettings
from backend.auth.oidc import OIDCError, OIDCProvider

ISSUER = "http://idp.local"
CLIENT_ID = "clouddesk-web"
KID = "test-key"


def _b64url(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": KID,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url(numbers.n),
        "e": _b64url(numbers.e),
    }
    return private_key, jwk


def _id_token(private_key, *, audience: str = CLIENT_ID) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": audience,
            "sub": "dex-user-1",
            "email": "demo@clouddesk.local",
            "name": "演示管理员",
            "iat": now,
            "exp": now + 300,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": KID},
    )


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, *, id_token: str) -> None:
        self.id_token = id_token
        self.posted: dict | None = None

    async def get(self, url: str) -> _Response:
        if url.endswith("/.well-known/openid-configuration"):
            return _Response(
                {
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/auth",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/keys",
                }
            )
        if url == f"{ISSUER}/keys":
            return _Response({"keys": [self.jwk]})
        return _Response({}, 404)

    async def post(self, url: str, data: dict) -> _Response:
        self.posted = data
        return _Response(
            {
                "access_token": "opaque-access-token",
                "id_token": self.id_token,
                "token_type": "Bearer",
                "expires_in": 300,
            }
        )

    async def aclose(self) -> None:
        return None


def _settings() -> AuthSettings:
    return AuthSettings(
        jwt_secret="test-secret-0123456789abcdef0123456789abcdef",
        oidc_issuer=ISSUER,
        oidc_client_id=CLIENT_ID,
        oidc_client_secret="test-client-secret",
        oidc_redirect_uri="http://localhost:3000/auth/callback",
    )


@pytest.mark.asyncio
async def test_oidc_provider_exchanges_code_and_maps_identity() -> None:
    private_key, jwk = _keypair()
    client = _FakeClient(id_token=_id_token(private_key))
    client.jwk = jwk
    provider = OIDCProvider(_settings(), client=client)

    identity = await provider.authenticate(code="code-1", code_verifier="verifier-1")

    assert identity.subject == "dex-user-1"
    assert identity.email == "demo@clouddesk.local"
    assert identity.name == "演示管理员"
    assert identity.tenant_slug == "clouddesk"
    assert client.posted is not None
    assert client.posted["code_verifier"] == "verifier-1"


@pytest.mark.asyncio
async def test_oidc_provider_rejects_wrong_audience() -> None:
    private_key, jwk = _keypair()
    client = _FakeClient(id_token=_id_token(private_key, audience="someone-else"))
    client.jwk = jwk
    provider = OIDCProvider(_settings(), client=client)

    with pytest.raises(OIDCError):
        await provider.authenticate(code="code-1", code_verifier="verifier-1")
