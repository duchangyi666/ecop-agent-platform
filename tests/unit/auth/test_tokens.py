from __future__ import annotations

from uuid import uuid4

import pytest

from backend.auth.tokens import InvalidToken, create_access_token, decode_access_token


def test_access_token_round_trip_returns_tenant_claims() -> None:
    tenant_id = uuid4()
    user_id = uuid4()

    token = create_access_token(
        tenant_id=tenant_id,
        user_id=user_id,
        actor_type="user",
        secret="unit-secret-0123456789abcdef0123456789abcdef",
        expires_minutes=30,
    )
    claims = decode_access_token(token, secret="unit-secret-0123456789abcdef0123456789abcdef")

    assert claims.tenant_id == tenant_id
    assert claims.user_id == user_id
    assert claims.actor_type == "user"
    assert claims.token_id


def test_access_token_rejects_wrong_secret() -> None:
    token = create_access_token(
        tenant_id=uuid4(),
        user_id=uuid4(),
        actor_type="user",
        secret="unit-secret-0123456789abcdef0123456789abcdef",
        expires_minutes=30,
    )

    with pytest.raises(InvalidToken):
        decode_access_token(token, secret="wrong-secret-0123456789abcdef0123456789abcdef")


def test_access_token_rejects_expired_token() -> None:
    token = create_access_token(
        tenant_id=uuid4(),
        user_id=uuid4(),
        actor_type="user",
        secret="unit-secret-0123456789abcdef0123456789abcdef",
        expires_minutes=-1,
    )

    with pytest.raises(InvalidToken):
        decode_access_token(token, secret="unit-secret-0123456789abcdef0123456789abcdef")
