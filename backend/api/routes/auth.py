from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.auth.config import get_auth_settings
from backend.auth.tokens import create_access_token
from backend.database.base import TenantScope
from backend.database.unit_of_work import UnitOfWork
from backend.api.dependencies import get_session_factory_dependency

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class AuthTokenRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    tenant_id: UUID
    user_id: UUID
    actor_type: Literal["user", "system"] = "user"


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(ge=1)


@router.post("/tokens", response_model=AuthTokenResponse)
async def issue_local_access_token(
    payload: AuthTokenRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> AuthTokenResponse:
    settings = get_auth_settings()
    if not settings.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "auth_not_configured",
                "message": "JWT_SECRET is not configured",
            },
        )

    scope = TenantScope(
        tenant_id=payload.tenant_id,
        actor_id=payload.user_id,
        actor_type=payload.actor_type,
    )
    async with UnitOfWork(session_factory, scope=scope) as uow:
        user = await uow.identity.get_user_in_tenant(
            scope=scope,
            user_id=payload.user_id,
        )
        if user is None or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "tenant_identity_invalid",
                    "message": "tenant identity is invalid",
                },
            )

    token = create_access_token(
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        actor_type=payload.actor_type,
        secret=settings.jwt_secret,
        expires_minutes=settings.token_expires_minutes,
    )
    return AuthTokenResponse(
        access_token=token,
        expires_in=settings.token_expires_minutes * 60,
    )


__all__ = ["AuthTokenRequest", "AuthTokenResponse", "router"]
