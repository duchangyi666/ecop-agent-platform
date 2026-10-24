from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.auth.config import get_auth_settings
from backend.auth.oidc import OIDCError, get_oidc_provider
from backend.auth.tokens import create_access_token
from backend.database.base import TenantScope
from backend.database.models.identity import Tenant, User
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


class AuthModeResponse(BaseModel):
    mode: Literal["dev", "jwt-only", "oidc"]
    oidc_configured: bool


class OIDCLoginConfigResponse(BaseModel):
    issuer: str
    authorization_endpoint: str
    client_id: str
    scopes: str
    redirect_uri: str
    mode: Literal["dev", "jwt-only", "oidc"]


class OIDCExchangeRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=4096)
    code_verifier: str = Field(min_length=43, max_length=128)
    redirect_uri: str | None = Field(default=None, max_length=500)


class OIDCExchangeResponse(AuthTokenResponse):
    tenant_id: UUID
    tenant_slug: str
    user_id: UUID
    display_name: str
    actor_type: str = "user"


@router.post("/tokens", response_model=AuthTokenResponse)
async def issue_local_access_token(
    payload: AuthTokenRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> AuthTokenResponse:
    settings = get_auth_settings()
    if settings.auth_mode != "dev":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "local_token_issuance_disabled",
                "message": "local token issuance is disabled in this auth mode",
            },
        )
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


@router.get("/mode", response_model=AuthModeResponse)
async def get_auth_mode() -> AuthModeResponse:
    settings = get_auth_settings()
    return AuthModeResponse(
        mode=settings.auth_mode,
        oidc_configured=settings.oidc_configured,
    )


@router.get("/oidc/config", response_model=OIDCLoginConfigResponse)
async def get_oidc_login_config() -> OIDCLoginConfigResponse:
    settings = get_auth_settings()
    if not settings.oidc_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "oidc_not_configured",
                "message": "OIDC is not configured",
            },
        )
    try:
        metadata = await get_oidc_provider().metadata()
    except OIDCError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "oidc_unavailable", "message": "OIDC provider is unavailable"},
        ) from exc
    return OIDCLoginConfigResponse(
        issuer=settings.oidc_issuer,
        authorization_endpoint=str(metadata["authorization_endpoint"]),
        client_id=settings.oidc_client_id,
        scopes=settings.oidc_scopes,
        redirect_uri=settings.oidc_redirect_uri,
        mode=settings.auth_mode,
    )


@router.post("/oidc/exchange", response_model=OIDCExchangeResponse)
async def exchange_oidc_code(
    payload: OIDCExchangeRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> OIDCExchangeResponse:
    settings = get_auth_settings()
    if not settings.oidc_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "oidc_not_configured", "message": "OIDC is not configured"},
        )
    redirect_uri = (payload.redirect_uri or settings.oidc_redirect_uri).rstrip("/")
    if redirect_uri not in settings.oidc_allowed_redirects:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_redirect_uri", "message": "redirect_uri is not allowed"},
        )
    try:
        identity = await get_oidc_provider().authenticate(
            code=payload.code,
            code_verifier=payload.code_verifier,
            redirect_uri=redirect_uri,
        )
    except OIDCError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "oidc_exchange_failed", "message": "OIDC login failed"},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    async with session_factory() as session:
        tenant = await session.scalar(
            select(Tenant).where(
                Tenant.slug == identity.tenant_slug,
                Tenant.deleted_at.is_(None),
            )
        )
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "tenant_not_provisioned", "message": "tenant is not provisioned"},
            )
        user = await session.scalar(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == identity.email,
                User.deleted_at.is_(None),
            )
        )
        if user is None or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "user_not_provisioned", "message": "user is not provisioned"},
            )

    token = create_access_token(
        tenant_id=tenant.id,
        user_id=user.id,
        actor_type="user",
        secret=settings.jwt_secret,
        expires_minutes=settings.token_expires_minutes,
    )
    return OIDCExchangeResponse(
        access_token=token,
        expires_in=settings.token_expires_minutes * 60,
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        user_id=user.id,
        display_name=user.display_name,
    )


__all__ = [
    "AuthModeResponse",
    "AuthTokenRequest",
    "AuthTokenResponse",
    "OIDCExchangeRequest",
    "OIDCExchangeResponse",
    "OIDCLoginConfigResponse",
    "router",
]
